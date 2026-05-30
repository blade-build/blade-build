# 依赖分析与 ninja 文件生成

BUILD 文件加载、`Target` 对象注册完成后，blade 把内存中的依赖图翻译成一
组 ninja 文件：一份根 `build.ninja`，加上若干由根文件 `include` 进来的
per-target `<pkg>/<name>.build.ninja`。这块实现的大半精力都花在**避免每
次重复做这些事**上——传递依赖展开与 per-target ninja 生成都被分析期内、
以及增量构建之间大量缓存。

| 文件 | 作用 |
| --- | --- |
| `src/blade/dependency_analyzer.py` | `expanded_deps`、拓扑排序、环检测 |
| `src/blade/build_manager.py` | 编排；per-target fingerprint 与 ninja 文件缓存 |
| `src/blade/backend.py` | 根文件头部、全局 rule、辅助模板 |
| `src/blade/target.py` | `generate_build` / fingerprint 计算 |
| `src/blade/util.py` | `write_if_changed` |

## 1. 依赖图

`Target.deps` 是 BUILD 中**声明**的依赖列表。分析阶段为之填出
`Target.expanded_deps`：拓扑稳定、去重后的传递依赖列表。

- `_expand_target_deps()` 沿 `deps` 递归，维护一个 per-walk 的
  `root_targets` 路径集合；再访问到正在展开中的 target 就报
  `Loop dependency` fatal，并指出造成环的那条边。
- `_unique_deps()` 去重时保持顺序（保留最后一次出现），保证与链接相关
  的相对位置不被打乱。
- 展开结果**记忆化到 target 上**：之后每个询问 `target.expanded_deps`
  的消费者都拿缓存值。反向（`expanded_dependents`）同一次扫描中同时填
  好，给少数需要的查询用。
- `_topological_sort()` 对全图跑 Kahn 算法。输出顺序很关键：为某个
  target 生成 ninja 时，可能需要它的依赖已经产出的信息（例如，一个
  `proto_library` 声明出来的生成头必须先可见，依赖它的 `cc_library` 才能
  写出 include 行）。

## 2. Per-target ninja 生成

每个 target 的 `generate()`（按子类各自实现）通过两个辅助产出 ninja
`build`/`rule` 语句：

- `Target.generate_build(rule, outputs, inputs, ...)`：构造一条 `build`
  语句，支持 `inputs`、`implicit_deps`（`|` 之后）、`order_only_deps`
  （`||` 之后）、`implicit_outputs`、以及 per-edge `variables`。结果追
  加到 target 内部的文本缓冲区。
- `_NinjaFileHeaderGenerator.generate_rule(name, command, ...)`（在
  `backend.py`）一次性声明全局 rule（cc、cxx、ar、link、proto、
  cxxhdrs、ccincchk…），带上常用字段（`depfile`、`deps`、`restat`、
  `pool`、`rspfile`）。

target 缓冲区里累积的文本写到 `<build_dir>/<path>/<name>.build.ninja`，
根 `build.ninja` 用普通 `include` 引入（不是 `subninja`——per-target 文件
是片段、共享全局 rule）。

## 3. 根 `build.ninja` 的结构

`_NinjaFileHeaderGenerator.generate()` 按固定顺序写根文件：

1. `ninja_required_version` 与 `builddir = ...`。
2. 全局 pool（例如一个 depth=1 的 `heavy_pool`，给某些不擅长并行的规则
   降速）。
3. 全部全局 ninja `rule` 声明——本工作区可能用到的所有 compile/link/
   codegen 规则，不论是否真的被某个 target 引用。
4. 一次性的 build 语句，比如 SCM stamp。
5. 按拓扑序对每个 per-target 文件 `include <path>.build.ninja`（依赖先
   于被依赖）。

被 compile rule 引用的两个 wrapper 脚本（POSIX 的 `cc_wrapper.sh`、
MSVC 的 `cc_wrapper.py`）以及被 `ccincchk` 消费的 pickle
`inclusion_declaration.data`，也是分析过程中按需写入构建目录的副产物，
首次引用时落盘。

## 4. 增量性

三层缓存协作来避免每次构建都重做：

**(a) Per-target fingerprint**：`Target.fingerprint()` 是一个 MD5，输入
熵字典里包含 blade 版本、config digest、srcs、直接 deps 的 fingerprint、
规则类型与规则的 `cmd`。每份 per-target ninja 第一行是
`#Fingerprint=<hash>`。重写之前 `build_manager` 读旧 fingerprint，相同
则**整文件原样复用**，对该 target 不做后续任何事。

**(b) `write_if_changed`**（`util.py`）：用于 cc wrapper、
inclusion-declaration pickle、per-target ninja 文件，以及（cc wrapper 内
部）`.incstk` 文件。把新字节与磁盘文件比较，**只有变化时才写**，否则保留
原 mtime。Ninja 的 `restat = 1` 利用保留下来的 mtime 去**剪掉**那些唯一
输入是"现在没变的 implicit output"的下游边（关于把这一链用在 `.incstk`
上的细节见 [hdrs check](hdrs_check.md)）。

**(c) 上文提到的 `expanded_deps` 记忆化**：传递依赖每个 target 在分析阶
段只走一次，不是每个消费者各走一次。

## 5. 技术细节与设计取舍

- **拓扑序是为了生成阶段，不是执行阶段。** ninja 完全按图自己调度执
  行。blade 排序只是为了在写某个 target 的 rule 前，能拿到来自其依赖
  的字段（如 `declared_genhdrs` 从 `proto_library` 传给 `cc_library`）。
- **生成头的 order-only deps（`||`）**到处都是。它保证生成器先于任何可
  能 `#include` 该生成头的编译运行，但**不**因生成器输出的 mtime 变化
  而强迫重编。配合生成器规则的 `restat`，得到"再生成但内容未变 → 不
  rebuild"的语义；真正基于内容的重新触发由编译器 depfile（`-MMD`）负
  责。
- **Per-target fingerprint 精确覆盖加载期输入。** 相同 fingerprint 的
  target 按构造产出相同 `.build.ninja` 文本，复用文件是安全的。不影响
  加载期输出的东西（如 `cc_test` 执行期参数）刻意不进 fingerprint。
- **请求集合之外的 target 也照样生成 ninja rule。** blade 需要它们，因
  为它们可能是请求 target 的传递依赖；`--no-test`、`--generate-package`
  是用于把会被牵涉进来的 test/package target 过滤出去的显式开关。
- **`pool = heavy_pool`** 取 `depth = 1`，是给少数对高并行不友好的工具
  （LTO 链接、大 proto codegen…）准备的：把它们路由到 1 宽的 pool，
  ninja 自动串行化。
- **包含检查也走同一套缓存。** `ccincchk` rule 的输入是各 compile rule
  的 `.incstk` implicit output。`write_if_changed` 在包含栈未真正变化时
  保留 mtime，ninja `restat` 据此在 `#include` 集合没动的重编上跳过检
  查——增量构建上一个可观的加速。

## 6. 用户体验优化要点

- **记忆化一次、多次查询。** `expanded_deps` / `expanded_dependents` 一
  趟算出、各处复用。"这东西依赖谁？"的代价从每次查询 O(图) 降到
  O(1)。
- **处处 `write_if_changed`。** per-target ninja、包含栈、wrapper 脚
  本、inclusion-declaration pickle——字节没变就不动盘。配合 ninja
  `restat`，"是否变化"的粒度从"文件被重写"细化到"文件内容不同"。
- **相同再生成不破坏 per-target ninja。** 对 BUILD 做一次无操作改动
  （空白、注释）若不改变 fingerprint，加载期之外不会产生额外代价。
- **错误指到本因。** `Loop dependency` 给出造成环的那条边并打印环走
  向；hdrs 检查中的缺依赖错误带出包含链；偶发的拓扑排序失败会指出无法
  解析的输入。在多千 target 的图上，一条糟糕的诊断很难调，所以这里在
  可读诊断上的投入是刻意的。
