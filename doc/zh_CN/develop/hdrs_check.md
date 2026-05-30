# C/C++ 头文件依赖检查（hdrs check）实现原理

从 Blade 2.0 起，C/C++ 的头文件也被纳入依赖管理：一个目标 `#include` 了某个头文件，就必须在 `deps` 里声明该头文件所属的库，否则 Blade 会在构建结束时报告问题。本篇讲述这套检查的**实现原理**；面向使用者的说明与修复指引见 [build_rules/cc.md](../build_rules/cc.md#修复-hdrs-引发的依赖缺失的检查问题)。

涉及的源码：

| 文件 | 职责 |
| --- | --- |
| `src/blade/cc_targets.py` | 收集"头文件 → 库"的声明、为每个目标落盘检查信息、生成检查规则 |
| `src/blade/build_manager.py` | 把全局声明写入 `inclusion_declaration.data` |
| `src/blade/backend.py` | 生成产出包含栈的编译命令（GCC：`cc_wrapper.sh` 加 `-H`；MSVC：`cc_wrapper.py` 旁路 `/showIncludes`）、`cxxhdrs` 与 `ccincchk` 规则 |
| `src/blade/inclusion_check.py` | 真正的检查逻辑（在构建期作为子进程被调用） |

---

## 一、实现机制

整个机制分三个阶段：**声明收集**（加载 BUILD 时）→ **信息落盘**（生成阶段）→ **产出包含栈并检查**（构建阶段）。

### 1.1 收集"头文件属于哪个库"的声明

加载 BUILD 文件时，每个 `cc_library` 把自己拥有的头文件登记到三张进程级全局表（`cc_targets.py`）：

- `declare_hdrs()` → `_hdr_targets_map`：**公开头文件**（`hdrs` 属性）→ 拥有它的库集合。
- `declare_hdr_dir()` → `_hdr_dir_targets_map`：**公开 include 目录**（如 `export_incs`、生成目录）→ 拥有它的库集合。
- `declare_private_hdrs()` → `_private_hdrs_target_map`：**私有头文件**（列在 `srcs` 里的 `.h`）→ 拥有它的目标集合。

一个头文件可以同时属于多个库，所以值都是集合。

所有 BUILD（含全部传递依赖）加载完毕后，`build_manager._write_inclusion_declaration_file()` 把这三张表连同 `allowed_undeclared_hdrs` 配置序列化到 `<build_dir>/inclusion_declaration.data`，供构建期的检查子进程读取。

### 1.2 为每个目标落盘检查信息（`.incchk`）

`cc_targets._write_inclusion_check_info()` 为每个 cc 目标写一个 `<target>.incchk`（pickle），包含检查所需的局部上下文：

- `deps`、`expanded_srcs` / `expanded_hdrs`（展开后的源文件与头文件列表）；
- `declared_hdrs` / `declared_incs`：本目标自身 **以及其 `deps`** 的公开头文件/公开目录（`_collect_declared_headers()`）——即"在本目标可见范围内合法的头文件"；
- `declared_genhdrs` / `declared_genincs`：从 `deps` 传递收集到的**生成头文件**（`_transitive_declared_generated_includes()`）；
- `severity`、`suppress`（来自配置）。

此外还会写一个 `<target>.incchk.extra`，内容是 `hdrs_deps` / `private_hdrs_deps` / `allowed_undeclared_hdrs`——这些是全局声明表的**局部子集缓存**，让检查子进程优先从小文件查询、避免每次都加载庞大的全局文件。它单独成文件，是为了不把"首次构建后才有的信息"混入 `.incchk` 而触发不必要的重复构建（见 [issue #1034](https://github.com/blade-build/blade-build/issues/1034)）。

`.incchk` **仅在内容变化时才重写**，以保持其 mtime 稳定，避免触发无谓的重新检查。

### 1.3 编译期产出"包含栈"（`.incstk` 文件）

检查需要知道每个源文件/头文件**实际**包含了哪些头文件。这一信息由编译器在编译时顺带产出：

- **源文件（GCC/Clang）**：每次编译都经由生成的包装脚本 `cc_wrapper.sh`（见 `backend.py`），它给编译命令追加 GCC 的 `-H` 选项，并用一段 awk 把"包含栈"从普通诊断里分离出来，写入 `<src>.incstk`。该路径通过每个目标文件各自的 `inclusion_stack` ninja 变量传入，因此与目标文件后缀（`.o` 还是 `.obj`）无关。
- **源文件（MSVC）**：见下方 MSVC 说明——在正常编译过程中顺带产出同样的 `.incstk`，无需单独预处理。
- **公开头文件（所有工具链）**：头文件从不被编译成目标文件，所以在**每种**工具链上都单独生成 `cxxhdrs` 规则，用预处理（GCC/Clang `-E`、MSVC `/P`）产出 `<hdr>.incstk`。这与下面的源文件路径无关——它是头文件获得包含栈的唯一途径。

`.incstk` 文件用**前导点的个数表示包含层级**，例如（GCC 格式）：

```text
. ./app/example/foo.h
.. build64_release/app/example/proto/foo.pb.h
... build64_release/common/rpc/rpc_service.pb.h
. ./common/rpc/rpc_client.h
```

MSVC 格式则为 `Note: including file:  <路径>`，用前导空格数表示层级。两种格式都由 `inclusion_check._parse_hdr_level_line()` 解析。

#### MSVC：旁路（tee）`/showIncludes`，而非单独预处理

GCC 的 `-H` 把包含栈写到 stderr，由 awk 包装脚本分流到 `.incstk`。MSVC 没有 `-H`，它输出 `/showIncludes` 行（`Note: including file: <路径>`）与诊断信息交织在一起，而 ninja 原生的 `deps = msvc` 本就要解析这些行来构建依赖图。为避免把每个源文件**编译两遍**（一遍出 `.obj` + 喂 ninja deps，一遍预处理出包含栈），MSVC 的 `cc`/`cxx` 规则用 `cc_wrapper.py` 包裹编译命令，对编译器输出做**旁路（tee）**：

- 把子进程的 stdout 与 stderr 合并到同一个管道（只读其中一侧会有管道缓冲死锁风险），逐行原样转发给 ninja 的 `deps = msvc` 解析器；
- 同时把 `Note: including file:` 行写入 `<src>.incstk`，于是同一次编译同时喂饱两个消费者。

有两类内容会被过滤，但处理方式**不同**：

- 编译器回显的**裸文件名**——这是 cl.exe 的怪癖，无法关闭。ninja 的 `CLParser::FilterInputFilename` 已经会**按扩展名过滤源文件**的回显（匹配 `.c/.cc/.cxx/.cpp/.c++`），所以 `cc`/`cxx` 规则无需我们插手；但它**不**过滤头文件扩展名，于是 `cxxhdrs` 的 `/P` 规则回显的 `foo.h` 会漏出来。因此我们自己丢弃任何单独的文件名 token（这也顺带覆盖 nvcc——它会回显 `.cu` 源文件名和中间临时文件名）。这类 token **两边都不发**——既不写入 `.incstk`，也不转发给 ninja——因为它不是 `Note: including file:` 行，deps 解析器并不需要它；
- **workspace 之外的绝对路径**（系统/SDK 头文件）：只从 `.incstk` 里滤掉（检查器本就会丢弃绝对路径，保留它们只会撑大文件、拖慢检查），**但仍转发给 ninja**——它的 `deps = msvc` 依赖图需要完整的 include 集合。

因此在 MSVC 上，包含栈是正常编译的副产物，与 GCC 上的 `-H` 完全一致——不需要对每个源文件单独预处理。

> **路径分隔符。** 后端写出的声明数据（`declared_hdrs`、全局 `public_hdrs` 表等）用的是操作系统分隔符，即 Windows 上的反斜杠，而 `/showIncludes` 路径已归一化为正斜杠。`inclusion_check.py` 在加载时把**所有**声明路径统一归一化为正斜杠（`_unix_path_set` / `_unix_path_dict` / `_unix_path_pairs`）来消除这一差异，使比较与分隔符无关、与产出数据的平台无关。

### 1.4 检查的触发（`ccincchk` 规则）

`cc_targets._generate_inclusion_check()` 为每个目标生成一条 `ccincchk` 规则：

```text
python -m blade.builtin_tools cc_inclusion_check <target>.incchk.result <target>.incchk
```

它的 implicit deps 是该目标所有的 `.incstk` 文件和目标文件，产物是 `<target>.incchk.result`（检查通过则写入 `OK`）。该结果文件被挂作链接步骤的 **order-only 依赖**——这样检查通过时不会触发重新链接，检查信息变化也只会重跑检查、不重链。

### 1.5 检查的执行（`inclusion_check.py`）

`ccincchk` 最终调用 `inclusion_check.check()`：

1. 载入目标的 `.incchk`（及 `.extra`），并按需 lazy 加载全局 `inclusion_declaration.data`。
2. 对该目标的每个源文件和头文件，找到对应的 `.incstk`，用 `_parse_inclusion_stacks()` 解析出：
   - **直接包含的头文件**（层级为 1、非绝对路径）；
   - **生成头文件**（路径位于 `build_dir` 下）：记录从源文件到该生成头的**完整包含栈**，并在此**停止下钻**——更深层的包含由其生成器（如 `proto_library`）自己保证；
   - **绝对路径**（系统头文件）：忽略。
3. 在解析结果上执行下面两类检查（第二、三节）。

---

## 二、检查机制：头文件未导出 / 私有头文件被跨库使用

这一类针对**直接包含**的头文件，在 `_check_direct_headers()` 中完成。对每个直接包含的头 `hdr`：

1. 若 `hdr` 在本目标的 `declared_hdrs` 中 → 合法，跳过。
2. 调用 `find_libs_by_header(hdr)` 查它属于哪个/哪些**公开**库：先按头文件精确匹配公开头表，匹配不到则**沿父目录逐级**匹配公开 include 目录表。
   - **查不到任何公开库**时，进一步判断它是不是某目标的私有头（`find_targets_by_private_hdr()`，即被列在某目标的 `srcs` 里）：
     - **是别的目标的私有头**（拥有者集合不含本目标）→ 报错：

       ```text
       "X" is a private header file of "//foo:bar"
       ```

       即**私有头文件被跨库使用**。私有头只允许其所属库自己包含；别的库要用，应由所属库把它放进 `hdrs` 导出为公开头。
     - **不是任何库的私有头**（也没被任何库导出）→ 视为**未声明/未导出**，报错：

       ```text
       "X" is not declared in any cc target. ...
       ```

       （除非该头文件在 `allowed_undeclared_hdrs` 或 `suppress` 名单中。）即这个头文件没有出现在任何库的 `hdrs` 或 `srcs` 里。
   - 查到了公开库 → 进入第三节的"直接依赖缺失"检查。

错误信息由 `_header_undeclared_message()`、`_hdr_declaration_message()`、`_or_joined_libs()` 拼装；其中 `_or_joined_libs()` 会把同目录的库简写成 `:name` 形式、其它写成 `//path:name`。

---

## 三、检查机制：引用头文件但未声明其所属库依赖

这一类是"包含了头文件，却没在 `deps` 里声明其所属库"，分**直接**与**间接**两种。

### 3.1 直接依赖缺失（Missing dependency）

仍在 `_check_direct_headers()`：当 `hdr` 找到了公开库拥有者集合 `libs`，但 `libs` 与 `deps ∪ {自身}` 的交集为空时 → 报错：

```text
<target>: Missing dependency declaration:
  In file included from "src/foo.cc",
    For "common/rpc/rpc_client.h", which belongs to "//common/rpc:rpc_client"
```

即你直接 `#include` 了某库的公开头，却没有在 `deps` 里依赖那个库。修复方法通常是把提示中的库加入本目标的 `deps`。

### 3.2 间接（生成头）依赖缺失（Missing indirect dependency）

在 `_check_generated_headers()` 中完成。对每条包含栈，取末端的**生成头文件** `generated_hdr`：

- 若它已作为直接包含头检查过 → 跳过；
- 若它被**传递声明**（在 `declared_genhdrs` / `declared_genincs` 中，即来自某个 `dep` 的 `generated_hdrs`）→ 合法；
- 否则 → 报错 `Missing indirect dependency declaration`，并打印从源文件一路向上到该生成头的**完整包含链**，方便定位是哪一环缺了依赖。

**为什么只对"生成头文件"做间接检查？** 生成头（`proto_library`、`gen_rule` 等的产物）如果依赖缺失，编译当前目标时这些头可能**还没生成**或**是过时版本**，从而造成编译错误，甚至更隐蔽的运行期错误。而非生成的头文件，其传递可见性由编译/链接过程天然保证，无需强制声明，故不做间接检查。

### 严重性与抑制

- `cc_config.hdr_dep_missing_severity`：检查问题的严重性（`error` / `warning`）。仅当为 `error` 且确有问题时检查才判定失败。
- `cc_config.hdr_dep_missing_suppress`：抑制升级前已存在的问题。
- `cc_config.allowed_undeclared_hdrs`：允许的未声明头文件白名单。

详见 [配置文件](../config.md#cc_config)。

---

## 设计取舍与边界

### 完备性的边界：配置敏感性

检查基于"单次构建里编译器实际走到的 `#include`"。`-H` / `/showIncludes` 只报告当前 `#ifdef` / `-D` / 目标平台与工具链下被**激活的分支**。因此：只在另一套配置下才需要的依赖（例如仅在 `#if defined(__linux__)` 或 `#ifdef DEBUG` 里包含的头），在当前构建中不会被观测到，漏声明也不会被发现。

这不是本机制独有的局限：Bazel 的沙箱有**完全相同**的盲区——它也只约束当前这次编译 action，没走到的分支同样管不到。任何"单配置观测"都无法做到跨配置完备。实践中的缓解办法是**依赖 CI 构建矩阵**：在 linux/mac、debug/release 等多套配置下各跑一遍，各自的检查叠加，逼近全局覆盖。

### 为什么用 `-H` 而不是 depfile

编译器的 `-MMD` depfile 已经列出一个翻译单元用到的全部头文件，但它是**扁平**的——只有集合、没有包含层级，无法区分"直接包含"与"被某个头间接包含"。而本机制的两类检查（第三节的「直接依赖缺失」与「间接/生成头依赖缺失」）恰恰依赖这个层级信息，所以必须使用能给出**包含树**的 `-H` / `/showIncludes`，而不能复用 depfile。

### 直接包含的判定：`-H` + 朴素源码扫描补丁

"直接包含的头"集合驱动了缺失依赖、私有头、未声明头、未用依赖这四个检查。blade 通过两个来源合并得出：

- **权威：`.incstk` 中 `-H` 的 depth-1 行**（`inclusion_check.py` 里的 `_parse_inclusion_stacks`）——编译器从这个源文件出发，在第 1 层实际遍历到的头。
- **补丁：正则源码扫描**——把源文件里所有字面 `#include "..."` / `#include <...>` 列出来（`_scan_source_includes`）。

二者按如下方式合并：

```text
direct_hdrs = depth-1 ∪ (source_scan ∩ all_paths_in_incstk)
```

与 `_read_all_incstk_paths(...)`（编译器在**任意**深度实际遍历过的路径）的**交集**是**关键的过滤门**：只要编译器没真正编译过的内容——块注释里的 `#include`、`#if 0` 块、未走的 `#ifdef` 分支、像 `#include "stdio.h"` 这样用引号误拼的系统头——都会自然在交集处掉出去，因为它们根本没进 `.incstk`。所以这里的扫描**有意保持朴素**：不剥注释、不解析 `#if 0`、不跟踪 `#ifdef`。试图在扫描里"聪明一点"要么是冗余（交集已经做了），要么是引入新的错误（比如盲目剥 `#if 0 / ... / #endif` 会把活的 `#else` 分支也吃掉）。

#### 为什么还需要这个补丁

`-H` 只在头**首次出现**的深度报告它；之后多重包含保护优化（multiple-include-guard optimization）会让后续 `#include` 不被读、也不在 `-H` 里出现。所以如果 `bar.cc` 里更早的 `#include`（例如它自己的 `bar.h`）已经传递性地拉入了 `foo.h`，那么 `bar.cc` 直接的 `#include "foo.h"` 在 `-H` 的 depth-1 上就消失了。没有补丁时，这种情况就被误判为"foo.h 不是直接包含"——未用依赖会出现响亮的误报，另外三个检查出现静默的漏报。详见 issue #1171。

#### 已知限制

"扫描 + 交集"不是真正的预处理器，有两个角落用例无法覆盖：

- **宏式包含**（`#define MY_HDR "x.h"` 后 `#include MY_HDR`）：正则只看到 `MY_HDR`，无法解析；`-H` 能覆盖，**除非**它同时被 guard 抑制——这个"双重小概率"的交集本设计接受。
- **既在 `#if 0` 又被另一条活路径传递包含**：交集会保留扫描结果，把它当成直接包含。效果是一个"冗余声明的"dep 逃过未用依赖检查，影响轻微。

此外，未用依赖检查会**豁免系统库**（键以 `#:NAME` 开头的依赖，如 `#:dl`、`#:pthread`）。这些系统库其实**也有头文件**（如 `<dlfcn.h>`、`<pthread.h>`），但 blade 没有维护一份"系统头 → 系统库"的映射（且这种映射本身就是平台/发行版相关、难以维护），所以基于头文件的检查无从评估它们——若不豁免就总是误报。同样地，**声明了 `hdrs = []` 的 header-less cc_library** 也会被豁免。

与上面"完备性边界"一节一致，hdrs 检查的根本依据是**当前这次构建里编译器实际用到的头**——补丁不改变这一原则，它只是修补 `-H` 自身在 depth-1 上撒谎的那一处（guard 抑制造成的丢失）。

### 与 Bazel 沙箱 / `layering_check` 的关系

Bazel 需要**两套**机制，才覆盖本机制用单一机制做到的事：

- **沙箱**在文件系统层面隔离：但一个 `.cc` 的沙箱必须包含其**传递闭包**的全部头文件（否则合法的传递包含会找不到文件）。因此沙箱只能拦住"包含了根本不在闭包里的头"（完全未声明），却**无法分辨**"直接包含了某个传递依赖（而非直接依赖）的头"这类 strict-deps 违规。
- **`layering_check`** 补上后者：它基于 Clang 的 module map + `-fmodules-decluse`（declared uses）——为每个库生成 module map 标注其头文件归属及到**直接依赖**的 `use` 边，由编译器在编译时强制"被包含的头必须来自已声明 `use` 的模块"。它是编译期、随普通编译附带（无需真正构建 `.pcm`），但**依赖工具链支持**：`-fmodules-decluse` 仅 Clang 提供，gcc 无等价物，故 Bazel 仅在 Unix/macOS 的 clang 上支持该特性。

本机制用**单一的"观测 + 所有权映射"**同时覆盖这两件事：`"... is not declared in any cc target"` 对应沙箱拦截的"完全未声明"，`libs ∩ (deps ∪ self) == ∅` 对应 `layering_check` 的"直接包含必须来自直接依赖"。而且因为它观测的是 `-H` / `/showIncludes` 的输出、而非依赖某个 Clang 专属的强制开关，所以在 **gcc、clang、MSVC** 上都能工作。

---

## 附录：相关产物文件

| 文件 | 内容 |
| --- | --- |
| `<build_dir>/inclusion_declaration.data` | 全局声明：公开头/公开目录、私有头、`allowed_undeclared_hdrs` |
| `<target>.incchk` | 单目标检查信息（deps、声明的头/目录、生成头声明、严重性等） |
| `<target>.incchk.extra` | 全局声明的局部子集缓存（避免加载大文件、避免触发重复构建） |
| `<target>.incchk.result` | 检查结果，通过时写入 `OK` |
| `<target>.incchk.details` | 编译器报告的直接/生成头集合，供下次构建构建 `.extra` 缓存 |
| `<src>.incstk` / `<hdr>.incstk` | 源文件/头文件的包含栈（`-H` / 预处理产出） |
