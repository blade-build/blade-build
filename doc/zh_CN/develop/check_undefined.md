# 静态未定义符号检查（`check_undefined`）实现原理

`cc_library` 是一个归档（`.a`/`.lib`），即使它引用了任何依赖都未提供的符号，链接器
也会照样把它打出来——错误要等到某个二进制链接它时才暴露。`check_undefined` 弥补这一
空档：它**不做共享链接**，逐库验证每个未定义外部符号都由该库声明的 `deps` 满足。本
文讲解它**如何实现**；面向用户的描述见
[build_rules/cc.md](../build_rules/cc.md#static-undefined-symbol-check)。

这是一个[实验性](https://github.com/blade-build/blade-build/issues/1225)特性，发现
项默认 `warning` 严重级。

涉及的源文件：

| 文件 | 职责 |
| --- | --- |
| `src/blade/cc_targets.py` | `_emit_archive_syms`（每归档一次 `nm`/`dumpbin`）与 `_generate_check_undefined`（收集每个目标的 spec） |
| `src/blade/build_manager.py` | `register_cc_check_undefined` / `cc_check_undefined_specs`——累积 spec；系统符号缓存 |
| `src/blade/backend.py` | `_emit_cc_check_undefined_batch`——写 manifest + 发射唯一的 `ccchkund_batch` ninja edge |
| `src/blade/builtin_tools.py` | `generate_cc_check_undefined[_batch]`——真正的符号集合差，构建期作为子进程运行 |
| `src/blade/toolchain.py` | `STATIC_LIB_SYMS_LABEL`、`ccsyms` rule（nm vs dumpbin）、默认链接库基线 |

---

## 1. 思路：一次算清的符号集合差

检查本质上是：**`undefined(lib) − defined(lib ∪ deps ∪ system) ⊆ allowlist`**。
实现的全部功夫都在于让这件事在大图上既廉价又可靠：

1. 符号读取器（`nm`，MSVC 上 `dumpbin`）**每归档只跑一次**，而非每个消费者跑一次。
2. 把每个归档的符号缓存到 `<archive>.syms` 文本文件（未定义 `#U` 段与归档内已定义
   `#D` 段）。
3. 为系统库预生成 `.syms` 格式的缓存。
4. 整个项目在**单个批处理子进程**里做集合差，而非每库一个 Python 进程。

## 2. 每归档的 `.syms`（`_emit_archive_syms`）

当 `cc_library` 产出归档时，`_emit_archive_syms` 发射一条 `ccsyms` ninja rule，跑一
次 `nm` 写出 `<archive>.syms`，并以工具链的 `STATIC_LIB_SYMS_LABEL` 记录。它是**幂
等**的——在同一目标上重复注册该 label 是空操作，所以一个归档绝不会被 nm 两次。MSVC
上归档是 COFF `.lib`，用 `dumpbin` 读；`.syms` 格式相同，故下游一切都与平台无关。

这是关键的伸缩手段：它"把过去 O(目标数 × 依赖数) 的 `nm` 调用，压缩到每归档总共一
次 `nm`"，因为依赖方读取其依赖缓存的 `.syms`，而非重新 nm 依赖的归档。

## 3. 每目标的 spec（`_generate_check_undefined`）

对每个 `cc_library`（除非被豁免——见 §6），这一步收集检查所需的输入，并在
BuildManager 上注册一个 *spec*：

- `target_syms` —— 该库自己的 `<archive>.syms`（既用于 `#U` 未定义集，也用于 `#D`
  已定义集）。
- `dep_syms` —— 每个传递性 `cc_library` 依赖的 `.syms`（只取 `#D` 集）。
- `sys_caches` —— 对每个系统库依赖（`path == '#'`），其预生成的符号缓存（经
  `get_system_symbol_cache` 解析，或挂在绝对路径库上），**外加**工具链的默认链接库
  基线（`get_default_linked_system_caches`——MSVC 上 msvcrt/ucrt/…，其它平台
  libc/libm/…）。去重，因为同一别名可能两处都出现。
- `allow_file` —— 每目标 + 全局的 `allow_undefined` 正则，写到 `<archive>.a.allow`
  附属文件，从而在 shell 引用与 ninja 变量替换中原样保留。

系统缓存这一步正是检查能**强制系统库纪律**的原因：`pow()` 只有当消费者声明了
`'#m'` 才解析得到，因为只有当 `#m` 是依赖时 libm 的符号才在 `sys_caches` 里。

## 4. 单个批处理 ninja edge（`backend._emit_cc_check_undefined_batch`）

不是每目标一条 `ccchkund` rule（那会在每次构建里*每库*付一次 Python 解释器启动开
销），而是累积所有 spec，待每个目标都 generate 之后由后端发射**唯一**一条
`ccchkund_batch` edge：

- spec 按 `target_label` 排序后序列化到
  `.cache/cc_check_undefined.manifest.json`（变更才写，因而 manifest 字节稳定、不会
  无端重触发）。
- edge 的显式输入是 manifest + 每个不同的 `.syms` 缓存（这样 ninja 恰在任一符号集变
  化时重跑批处理）；`.allow` 文件作为 implicit deps。
- 输出是一个 stamp 文件，且**不声明 `default`**——ninja 会自动构建叶子输出，故 stamp
  无需覆盖 ninja 的叶子发现即可被构建到（覆盖会破坏 `blade build //some:target`）。
- **缓存式 regen** —— 若本次运行每个 cc_library 的子 ninja 都被复用，则没有 spec 注
  册，但磁盘上前一次的 manifest 会被重新发射，使主 `build.ninja` 的 regen 保持幂
  等。真的无可检查时（MSVC 且全部豁免、或没有 manifest），则什么也不发射。

由于该 stamp **没有消费者**（没有构建节点依赖其结果），批处理不会与构建其余部分串
行——它并行运行，只负责*报告*。

## 5. 检查本身（`builtin_tools`）

`generate_cc_check_undefined_batch` 在构建期作为 `ccchkund_batch` 子进程运行。对每
个 spec，它加载 `.syms` 文件，计算
`undefined − (own_defined ∪ dep_defined ∪ system_defined)`，丢弃匹配任一
`allow_undefined` 正则的项，并以配置的 `severity` 报告余下的。非批处理的
`generate_cc_check_undefined` 是针对单目标的同一逻辑（为清晰/直接调用而保留）。

## 6. 豁免与不运行的情形

`_generate_check_undefined` 在以下情况提前返回（不注册 spec）：

- 目标上 `check_undefined = False`（命令行 `--cc-check-undefined` /
  `--no-cc-check-undefined` 与 `cc_library_config.check_undefined` 设默认值；每目标
  的 `False` 永远优先——见 `CcTarget.__init__` 里的三态解析）。
- `allow_undefined = True` —— 旧式"按设计就有未解析符号、由消费者在最终链接时提供"
  的信号，它在链接期同样关闭 `-Wl,--no-undefined`；静态检查会与之矛盾。（*列表*形式
  的 `allow_undefined` 是允许清单，作为正则继续走检查。）

它对 `generate_dynamic` 库也会运行：动态链接的 `-Wl,--no-undefined` 是最终裁决，但
静态检查在任何链接运行*之前*就逐库捕获同样的遗漏，反馈更快（#1225）。MSVC 上经
`dumpbin` 工作，CRT 由默认链接库基线覆盖，因而 `/DEFAULTLIB` 指令不会误报。
