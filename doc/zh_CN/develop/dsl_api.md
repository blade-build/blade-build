# 内置函数与 `blade.*` DSL

BUILD 文件是一段在严格受控命名空间里跑的 Python 脚本。命名空间里有两类
东西：**规则函数**（`cc_library`、`proto_library`…）和注入的 `blade` 模
块，后者只暴露 BUILD 文件正当需要的少量辅助（路径处理、读 config、写日
志、查环境）。除此之外，Python 主机带来的能力要么被去掉，要么换成更安
全的版本。

| 文件 | 作用 |
| --- | --- |
| `src/blade/build_rules.py` | 规则注册表（`register_function`、`get_all`） |
| `src/blade/dsl_api.py` | 给 BUILD 文件用的 `blade` 模块 |
| `src/blade/restricted.py` | 安全 builtins 集合（`safe_builtins`） |
| `src/blade/blade_types.py` | 规则参数共享类型别名 |
| `src/blade/util.py` | `var_to_list` / `var_to_list_or_none` 归一器 |

## 1. 规则注册

每一种规则（`cc_library`、`cc_binary`、`py_library`、`proto_library`、
`gen_rule`、…）都只是某个 `*_targets.py` 模块里的一个 Python 函数。模块
导入时，文件里写有 `build_rules.register_function(cc_library)` 之类的调
用，把名字塞进一个全局注册表。

一次 `blade` 调用里，`_load_build_rules()` 按固定顺序导入这些语言模块，
注册表填充一次。之后 `build_rules.get_all()` 返回那张扁平 dict，成为每
个 BUILD 文件 globals 的基础（见
[BUILD 文件加载](build_file_loading.md)）。

同样这张 dict 还包装成一个 "native" 对象。通过 `load()` 加载的扩展能用
`native.cc_library` 拿到规则 —— 在扩展自身的命名空间中 `cc_library` 本
身并不是 global（避免覆盖用户自己定义的同名函数）。这种"BUILD ↔ 扩展"
的分割让扩展的表层小，又不剥夺那些真正需要调用规则的扩展。

## 2. `blade` 模块

`dsl_api.get_blade_module()` 在每个 BUILD 加载时构造一个轻量模块对象，暴
露：

- **`blade.config`** —— `get_item(section, item)` 与 `get_section(name)`，
  与 [configuration](configuration.md) 中描述的 getter 一致。
- **`blade.console`** —— `debug` / `info` / `notice` / `warning` /
  `error`，走 blade 通用诊断通路。BUILD 中的输出与其它 blade 输出风格
  与源位置前缀一致。
- **`blade.path`** —— 精选的 `os.path` 子集（`abspath`、`basename`、
  `dirname`、`exists`、`join`、`normpath`、`relpath`、`splitext`）。会
  不小心越界 stat 或写文件的成员一概不暴露。
- **`blade.workspace`** —— 当前工作区的 `root_dir` 与 `build_dir`。通过
  这个固定句柄读取，避免 BUILD 通过别的旁路碰单例。
- **`blade.host_os` / `blade.host_arch`** —— 运行 blade 的机器的描述字
  符串。便于按主机条件化 `srcs`。
- **`blade.build_type`** / **`blade.build_type_is_debug()`** —— 当前
  profile。
- **仅构建期可用的句柄**：
  - `blade.current_source_dir()` / `blade.current_target_dir()`：当前
    BUILD 的包路径及其构建目录映像，来自驱动 target 键的同一个 thread-local。
  - `blade.cc_toolchain`：活动工具链的只读代理（`obj_suffix`、
    `lib_prefix`、`tool('cxx')`、…）。让 BUILD 能按工具链参数化文件名，
    不必导入内部类。
- **仅配置期可用的句柄**：
  - `blade.getenv(name, default=None)` —— 在 `BLADE_ROOT` 中读取环境变量。
    全 blade 唯一被授权的 env 访问入口；BUILD 文件调用会以 `console.fatal`
    终止并指向 BUILD 期等价物（`blade.cc_toolchain.tool('cc')` 或
    `blade.config`）。把 env 读取收敛到配置层，所有 env 依赖集中在一个
    可审计文件里，BUILD 文件保持 hermetic。

其中一部分属性被标为 `_BUILD_ONLY_ATTRS`：在 `BLADE_ROOT`（配置阶段）里
读它们会触发清晰报错，提示"此时工具链还不存在，若想延后求值请传一个
lambda"。这是减少用户困惑的诊断之一。对称地，`getenv` 在方法体内自己做
`if not self._config_phase: console.fatal(...)`——`_BUILD_ONLY_ATTRS`
那套基于 `__getattr__`，对 `_BladeModule` 上的方法不起作用，所以放在方法
里手判。

## 3. 沙箱

`global_config.restricted_dsl` 打开（默认开）时，每个 BUILD 文件的
`__builtins__` 被替换为 `restricted.safe_builtins`：

- **允许**：类型构造（`int`、`list`、`dict`、`str`、`set`、`tuple`、
  `bool`…）、stdlib 安全那一端（`len`、`isinstance`、`hasattr`、
  `enumerate`、`zip`、`sorted`、`range`…）。
- **禁用**：`__import__`、`exec`、`eval`、`compile`、`execfile`、
  `subprocess`、`os.system`、写文件。每个被禁的名字替换为一个 wrapper，
  调用时抛 `BuildFileError`，错误信息里带用户 BUILD 的源位置。
- **收窄**：`open()` 限定为只读。

BUILD 仍是 Python，用户可以写循环、列表推导、辅助函数；只是不能跨出沙
箱去启进程、拉网络、`import` 任意模块。结果是：加载快（不会有意外的子进
程启动、无全局副作用），且 BUILD 行为完全由文本 + 工作区可复现。

## 4. 参数类型与归一化

`srcs`、`hdrs`、`deps`、`incs` 等规则参数在 `blade_types.py` 中被标为
`StrOrList` / `StrOrListOpt`。这些别名服务于文档与静态分析；运行时每个
规则入口都把值过一遍 `util.var_to_list()`（或 `_or_none` 变体）：

- 接受单个 `str`、`list`/`tuple`/`set`、或 `None`。
- 返回**新的** `list[str]`（避免之后对 target 属性的就地改动回流到用户
  给出的列表）。
- 保留 `None` ↔ `[]` 的区别：`var_to_list(None) -> []`，
  `var_to_list_or_none(None) -> None`。某些属性（如 `hdrs`、
  `visibility`）选用后者，blade 才能区分"用户没说"与"用户明确说空"——
  例如 `hdrs = []` 是声明"header-less 库"、把它从未用依赖检查中豁免出
  来的方式（见 [hdrs check](hdrs_check.md)）。

## 5. 技术细节与扩展点

- **新增一种规则**机械上就是写 `def my_rule(name, ...): ...` 加上模块
  顶层 `build_rules.register_function(my_rule)`，再让
  `load_build_files._load_build_rules()` 导入该模块。函数体通常构造一个
  `Target` 子类、由它调用 `register_target`。
- **`include()` 与 `load()`** 继承当前 BUILD 的 globals —— 不会每次新建
  沙箱，所以 `include` 进来的文件相当于把其代码直接拼到调用处。`load()`
  更严格：只导出明确点名的符号，扩展作用域保持干净。
- **延后求值的 callable config 值** —— 若 `cc_config` 某项需要解析时已
  有工具链信息，`BLADE_ROOT` 中推荐写
  `lambda blade: ...`，由 `_DeferredConfigValue` 在 `cc_targets.py` 查询
  时再调用。配置阶段读 `blade.cc_toolchain` 会触发一条带 lambda 提示的
  报错，避免用户从堆栈里去推这条惯例。
- **所有诊断都带源位置。** 受限 builtin 违规、`glob()` 失败、类型错
  误、注册冲突都过 `console.diagnose()`，前缀是 BUILD 路径加行号。所以
  `srcs=['foo.c']` 拼错（文件不存在）会精确指到规则调用所在的 BUILD
  行，而不是 blade 内部某处。
