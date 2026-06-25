# 自定义规则（`define_rule`）实现原理

`define_rule` 让 `.bld` 扩展可以声明一个**全新的规则类型**——带类型化的属性，加
上一个声明输出、生成构建 edge 的 Python *action*——而无需改动 Blade 核心。本文讲
解它**如何实现**；面向用户的 API 见
[build_rules/custom_rule.md](../build_rules/custom_rule.md)。

这是一个[实验性](https://github.com/blade-build/blade-build/issues/829)特性，API
仍可能变化。

涉及的源文件：

| 文件 | 职责 |
| --- | --- |
| `src/blade/custom_rule_target.py` | 整个特性：`attr` 命名空间、传给 action 的 `ActionContext` / `_Actions`、通用的 `CustomRuleTarget`，以及 `define_rule` 内置函数 |
| `src/blade/build_rules.py` | `register_extension_variable`——让 `define_rule` / `attr` **仅在 `.bld` 文件中可见** |
| `src/blade/gen_command.py` | 命令模板展开（`$SRCS` / `$OUTS` / …）与平台选择，与 `gen_rule` 共用 |
| `src/blade/rule_registry.py` | `register_rule_provider`——`ctx.actions.shared_rule` 写入的共享 ninja rule 槽位 |
| `src/blade/cc_targets.py` | `declare_hdrs` / `declare_hdr_dir`——`provides_cc` 规则生成的头文件如何流向 `cc_*` 依赖 |

---

## 1. 为什么是规则，而非宏

[宏](../build_rules/extension.md)——`.bld` 里调用现有规则的普通函数——能覆盖简单
复用，但它无法*声明新的、能被其它目标在分析期看到的输出*。一个依赖代码生成器的
`cc_library`，需要生成的头文件在它自己 `generate()` 运行**之前**就作为已声明的输
出存在，这样头文件对包含检查和 include 路径才可见。`define_rule` 正是为此而生：它
仿照 [Bazel 的规则](https://bazel.build/extending/rules)，但刻意做得更小——只有一
个 `action`，除了 `cc_*` 头文件流之外没有 provider 系统。

## 2. 仅 `.bld` 可见

`define_rule` 和 `attr` **不在** BUILD 文件的全局名字里。它们被注册为*扩展*变量：

```python
build_rules.register_extension_variable('define_rule', define_rule)
build_rules.register_extension_variable('attr', attr)
```

`build_rules.get_all_for_extension()` 只把它们注入到经 `load` 加载的 `.bld` 的全
局名字里，其它地方一概没有。这一处注册就是"自定义规则只能在扩展中定义"的全部约束
——BUILD 文件里写 `define_rule` 只会得到 `NameError`。`define_rule` 返回的是一个普
通可调用对象，所以一旦 `load` 进来，它就像原生规则一样在 BUILD 里被调用。

## 3. 属性 schema（`attr`）

`attr` 是单例 `_AttrNamespace`；每个方法（`attr.string`、`attr.bool`、`attr.int`、
`attr.string_list`、`attr.src_list`、`attr.dep_list`、`attr.out_list`）返回一个可
序列化的小 `Attr`（`kind`、`default`、`mandatory`、`exts`）。`Attr` 刻意**不持有任
何 callable 或复杂对象**——只有 kind 字符串、朴素默认值和布尔值——这样 schema 可以
直接进入目标的指纹（见 §7）而不引入不可哈希的熵。

构造时有两种 kind 被特殊处理，因为它们喂给 Blade 自己的目标字段而非 action 的
`ctx.attrs`：

- `src_list` → 拼接进目标的 `srcs`（可用 `exts` 做扩展名过滤）。
- `dep_list` → 合并进目标的 `deps`。

其余都落进 `ctx.attrs[name]`。`name` / `deps` / `visibility` / `tags` 永远可用，无
需声明。

## 4. 目标：`CustomRuleTarget`

`define_rule` 返回一个轻量的 `rule_fn(name, deps, visibility, tags, **kwargs)`，
它在每次 BUILD 调用时构造一个 `CustomRuleTarget`，并通过
`build_manager.instance.register_target()` 注册。

`CustomRuleTarget.__init__` 完成 schema 工作：

1. 对每个声明的属性，取出传入值（或取默认值），记录**缺失的 mandatory** 错误，并
   `_coerce` 成声明的 kind——类型不符时**记录错误而非抛异常**，这样所有 schema 问
   题在 `super().__init__` 之后一并暴露。
2. 把 `src_list` / `dep_list` 路由到 `srcs` / `deps`；其余进入一个 `custom` dict，
   存为 `self.attr['custom_attrs']`。
3. `attr_values` 里剩下的就是**未知属性** → 报错。
4. 目标 type 为 `'custom:' + rule_type`，并打上 `type:custom_rule` 标签。

## 5. action 在分析期运行

最关键的设计选择仿照 Bazel：**action 在构造时（仍属分析期）运行**，而不是在
`generate()`：

```python
self._action(ActionContext(self))      # 在 __init__ 中
if not self._outputs:
    self.error('custom rule "%s" action declared no outputs' % rule_type)
```

为什么现在跑：action 的 `declare_header` / `declare_inc_dir` 必须在任何依赖目标
generate **之前**把生成的头文件注册进 `cc_*` 头文件映射——和 `gen_rule`、
`proto_library` 完全一致。所以 action 被一分为二：

- **输出声明立即发生。** `ctx.declare_output(name)` 追加到 `self._outputs` 并经
  `_add_target_file` 以索引标签注册该文件。`ctx.declare_header` 额外调用
  `cc_targets.declare_hdrs(self, [name])` 并记录 `generated_hdrs`；
  `ctx.declare_inc_dir` 调用 `declare_hdr_dir` 并记录
  `generated_incs` / `export_incs`——但仅当规则定义时 `provides_cc=True`。
- **构建 edge 此刻只被*记录*，稍后再 flush。** `ctx.actions.run_shell` /
  `ctx.actions.run` 把一个 `functools.partial` 追加到 `self._pending_edges`，而不
  立即发射，因为构造期依赖图尚未完全解析。`generate()` 再重放它们：

  ```python
  def generate(self):
      for flush in self._pending_edges:
          flush()
  ```

  到 `generate()` 时 `expanded_deps` 和依赖输出文件都已就绪，`implicit_deps` 才能
  正确解析。

`ActionContext` 暴露读取侧（`ctx.name`、`ctx.attrs`、`ctx.toolchain`、
`ctx.config(section)`、`ctx.deps_outputs()`、`ctx.deps_generated_headers()`）；
`_Actions`（`ctx.actions`）暴露发射侧。

## 6. edge 发射复用 `gen_rule` 机制

`_emit_shell_edge` 是 `run_shell` 的核心，刻意与 `gen_rule` 用同一条流水线：

1. `gen_command.select_command(command, cmd_bash, cmd_bat)` 选平台变体（通用 host
   shell / bash / bat）。
2. `gen_command.expand_vars(...)` 展开 `$SRCS` / `$OUTS` / `$OUTS[i]` /
   `$SRC_DIR` / `$OUT_DIR` / `$BUILD_DIR`。这里 **`first_vars=False`**，所以已废弃
   的 `$FIRST_SRC` / `$FIRST_OUT` 不可用——自定义规则用 `$SRCS[0]` / `$OUTS[0]`。
3. `gen_command.wrap_command(...)` 为所选 shell 包装命令。
4. 写一条唯一命名的 per-target ninja rule（`_rule_name()` 加序号后缀，使一个
   action 里的多条 edge 不冲突），再由 `generate_build(...)` 发射构建 edge。
   `outputs` 默认是至此声明的全部输出；`inputs` 默认是展开后的 `srcs`。

`ctx.actions.shared_rule(ninja_rule)` 是多条 edge 共享一条 rule 的方案：它把 rule
**只注册一次**到 registry 的 custom 槽位
（`rule_registry.register_rule_provider(..., name='custom:'+ninja_rule.name)`，
按名字幂等），`ctx.actions.run(rule, ...)` 再经 `_emit_edge` 发射引用它的 edge。

## 7. 指纹——为何 action 必须自包含

目标指纹决定增量重建。`CustomRuleTarget` 在 `_fingerprint_entropy` 里同时纳入
schema 与 **action 的源码**：

```python
entropy['custom_rule_action'] = self._action_fingerprint()
entropy['custom_rule_schema'] = sorted(
    (k, a.kind, repr(a.default), a.mandatory, tuple(a.exts or ())) ...)
```

`_action_fingerprint` 对 `inspect.getsource(self._action)` 加上 action 所在文件的
md5 做哈希。这正是 V1 限制**"action 要自包含在它的 `.bld` 里"**的由来：action 从其
它 `.py` 模块 import 的辅助函数*不*在这份指纹里，所以改它们不会触发重建。schema 之
所以可序列化，正是为了能在这里无特殊处理地加入熵。

## 8. 由设计自然导出的限制

- **仅 `.bld`**——§2 的直接后果（内置函数不在 BUILD 全局里）。
- **没有通用 provider**——跨规则数据仅限 §5 的 `generated_hdrs` /
  `generated_incs` 流，因为那是唯一接入 `cc_*` 消费的通道。
- **action 自包含**——见 §7。
- **生成的头文件在 system/SDK 路径之后解析**，所以与系统头同名的输出名会被遮蔽；
  规则无法重排 include 路径顺序。
