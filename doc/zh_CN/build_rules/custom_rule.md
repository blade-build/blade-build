# 自定义规则（`define_rule`）

> **实验性。** API（`define_rule` / `attr` / action 的 `ctx`）在未来版本可能变化。
> 见 [#829](https://github.com/blade-build/blade-build/issues/829)。

简单的复用用[宏](extension.md)（`.bld` 里一个调用 `gen_rule` 等现成规则的普通函数）就够了。
当你需要一个**真正的新规则类型**——带类型化属性 + 用 Python *action* 计算输出并产出构建命令
——就用 `define_rule`。它借鉴了 [Bazel rules](https://bazel.build/extending/rules) 的形态，但刻意更精简。

## 快速示例

假设你开发了一门 awesome 语言，它的编译器是 awesomec，生成 C++。

`//myrules/awesome.bld`：

```python
def _impl(ctx):
    out = ctx.declare_output(ctx.name + '.cc')          # 声明一个输出
    if ctx.attrs['gen_header']:
        ctx.declare_header(ctx.name + '.h')             # cc_* 可消费的头文件
    ctx.actions.run_shell(command='awesomec $SRCS -o $OUTS', outputs=[out])

awesome_library = define_rule(
    name='awesome_library',
    attrs={
        'srcs': attr.src_list(exts=['awesome']),
        'opt':  attr.string(default='-O2'),
        'gen_header': attr.bool(default=True),
    },
    provides_cc=True,
    action=_impl,
)
```

`//demo/BUILD`：

```python
load('//myrules/awesome.bld', 'awesome_library')

awesome_library(name='demo', srcs=['demo.awesome'])
cc_binary(name='app', srcs=['main.cc'], deps=[':demo'])   # 自动拿到 demo.h / demo.cc
```

## `define_rule`

`define_rule` 是**仅在 `.bld` 扩展文件中可用的 builtin**（`attr` 同理；两者在 `BUILD`
文件里都不可见）。把它的返回值绑定到一个名字，`load` 才能导入：
`awesome_library = define_rule('awesome_library', ...)`。

```python
define_rule(name, attrs=None, action=None, provides_cc=False, description='CUSTOM')
```

- `name`：str，规则类型 / 生成的 BUILD 函数名。
- `attrs`：dict，属性名 → `attr.<kind>(...)`（见下）。`name`、`deps`、`visibility`、
  `tags` 始终可用，无需声明。
- `action`：可调用对象 `action(ctx)`——在分析期运行，用于声明输出、登记构建边（见*action*）。必填。
- `provides_cc`：bool，为 True 时 action 声明的头文件 / include 目录会流向依赖它的
  `cc_*` 目标（经 `generated_hdrs` / `generated_incs`）。
- `description`：str，产出边的默认进度标签。

## 属性（`attr`）

| 种类 | 值 | 说明 |
|---|---|---|
| `attr.string(default='', mandatory=False)` | str | |
| `attr.bool(default=False)` | bool | |
| `attr.int(default=0)` | int | |
| `attr.string_list(default=())` | list[str] | |
| `attr.src_list(default=(), exts=None)` | list[str] | 成为规则的 `srcs`；`exts` 限制扩展名 |
| `attr.dep_list(default=())` | list[str] | 并入规则的 `deps` |
| `attr.out_list(default=())` | list[str] | 输出名列表（由 action 声明） |

`mandatory=True` 使属性必填。未知属性、缺失的必填属性、类型不符都会报错。

## action

`action(ctx)` 在**分析期**运行（BUILD 加载时）：它只*声明输出*和*登记构建边*——不执行命令、
不读写文件（那些发生在之后的构建期）。在这个阶段声明输出，正是依赖者能看到本规则生成头文件的前提。

`ctx` 读状态：

- `ctx.name`、`ctx.path`、`ctx.fullname`、`ctx.build_dir`、`ctx.target_dir`
- `ctx.attrs`——校验后的属性值（`src_list` 已展开为路径）
- `ctx.toolchain`、`ctx.config(section)`
- `ctx.deps_outputs()`——deps 的输出文件
- `ctx.deps_generated_headers()`——deps 生成头的 `(files, dirs)`

`ctx` 输出声明：

- `ctx.declare_output(name)` → 返回输出文件的完整路径
- `ctx.declare_header(name)` → 同 `declare_output`，且（当 `provides_cc`）把该头暴露给依赖的 `cc_*`
- `ctx.declare_inc_dir(inc)` → 把一个生成的 include 目录暴露给依赖者

`ctx.actions`——产出构建边：

- `ctx.actions.run_shell(command=None, cmd_bash=None, cmd_bat=None, inputs=None,
  outputs=None, implicit_deps=None, variables=None, description=None)`——产出
  每目标 rule + 构建边。`command` 是通用形式（宿主 shell）；`cmd_bash` / `cmd_bat`
  是可选的平台变体（选择规则同 [`gen_rule`](gen_rule.md)）。命令可用 `$SRCS`、`$OUTS`、
  `$OUTS[i]` / `$SRCS[i]`（按下标或名字）、`$SRC_DIR`、`$OUT_DIR`、`$BUILD_DIR`。
  （已废弃的 `$FIRST_SRC` / `$FIRST_OUT` 在这里**不支持**——请用 `$OUTS[0]` / `$SRCS[0]`。）
  `outputs` 默认为目前已声明的全部输出；`inputs` 默认为规则的 `srcs`。
- `ctx.actions.run(rule, inputs=None, outputs=None, …)`——产出引用由 `shared_rule`
  注册的共享 rule 的构建边。
- `ctx.actions.shared_rule(ninja_rule)`——注册一条共享 ninja rule
  （`blade.ninja_rule.NinjaRule`）一次，供多条边 / 多个目标引用。

## 局限（V1）

- `define_rule` 只在经 `load` 加载的 `.bld` 文件中可用，不能在 `BUILD` 里用。
- 每目标构建缓存以 action 源码及其 `.bld` 文件为指纹，所以**让 action 自包含在 `.bld` 内**；
  从其它 `.py` 模块导入的 helper 不会被跟踪。
- 暂无通用 provider 机制——跨规则数据仅限流向 `cc_*` 的 `generated_hdrs` / `generated_incs`。
- 生成头在系统 / SDK include 路径之后被搜索，因此避免与系统头同名的输出名。
