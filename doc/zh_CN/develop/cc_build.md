# C/C++ 程序是如何构建的

C/C++ 流水线有四块：**工具链抽象**把 GCC/Clang 与 MSVC 的差异藏到一个小
接口背后；**编译规则生成器**为各工具链烘焙模板；**per-target 的 flag 与
include 路径合成**；以及**链接规则的构造**。头文件依赖检查是一个独立子
系统，见 [hdrs check](hdrs_check.md)。

| 文件 | 作用 |
| --- | --- |
| `src/blade/toolchain.py` | `GccToolChain` / `MsvcToolChain` 抽象、vendor 检测 |
| `src/blade/backend.py` | `cc` / `cxx` / `ar` / `link` / `solink` rule 输出 |
| `src/blade/cc_targets.py` | per-target flag/include 合成、库顺序 |
| `src/blade/cu_targets.py` | CUDA 路径；继承 `CcTarget` |
| `src/blade/build_accelerator.py` | ccache/distcc 的 wrapper 接口 |

## 1. 工具链抽象与选择

抽象 `ToolChain` 定义了所有消费者依赖的"形状"：文件名形态
（`obj_suffix`、`lib_prefix`、`static_lib_suffix`、`dynamic_lib_suffix`、
`exe_suffix`）、库命名（`static_library_name(name)`、
`dynamic_library_name(name)`）、工具取用（`get_cc()`、`get_cxx()`、
`get_ar()`），以及小型 vendor 查询（`cc_is('clang')`）。两个具体实现：

- **`GccToolChain`** —— Linux/macOS 使用。会探测编译器 `--version` 输出
  以确定 `cc_vendor`（gcc、clang、apple-clang…），让后续 flag 逻辑能按
  真实 vendor 分支，而不只是"像 gcc / 不像"。这关键点在于：macOS 的
  Apple Clang 伪装成 `gcc`，少数 GNU 专属 flag（如 `--whole-archive`）
  否则会被发到一个并不识别它们的 linker。
- **`MsvcToolChain`** —— 仅 Windows。定位 Visual Studio + Windows SDK
  （从注册表或 `vswhere.exe`），把请求的目标 arch 映射到正确的工具目
  录，并暴露系统库路径，便于链接步骤输出正确的 `/LIBPATH:`。

`create_toolchain()` 选择顺序：显式 `--cc-toolchain=` CLI、
`cc_config.toolchain`、任意 `cc_toolchain_config()` 条目、按平台自动检
测。选定的工具链成为所有 cc target 共享的单例。

加速器（`build_accelerator.py`）包了一层编译器取用，便于将来插入
ccache/distcc 前缀；当前实现透传工具链命令，但接缝已留好。

## 2. 编译规则

`backend.py` 生成全局 ninja rule `cc`、`cxx`、（如配置启用）`secretcc`，
再加上头文件检查所需的 `cxxhdrs` 与 `ccincchk`。

**GCC/Clang 形态** —— 命令模板大约是
`cc -o ${out} -MMD -MF ${out}.d -c -fPIC ${cflags} ${cppflags} ${includes}`，
外面套 `cc_wrapper.sh` 顺便产出包含栈（详见 [hdrs check](hdrs_check.md)）。
`-MMD` 是 depfile 机制，ninja 通过 `deps = gcc` 消费它追踪头文件变化；
这与基于包含栈的检查互相独立。

**MSVC 形态** —— 把 `-MMD` 换成 `/showIncludes`，ninja 用 `deps = msvc`
解析；`cc_wrapper.py` 旁路再 tee 一份到 `.incstk`，让头文件检查在
Windows 上有相同形状的输入。`cxxhdrs` rule 另用 `/P`（预处理到文件）+
`/showIncludes`，让头文件不必编译就能检查。含空格路径用 `/I"path"` 包
裹，因 MSVC 解析器对此敏感。

`backend.py` 也把全局内禀 flag（`-pipe`、`-fno-omit-frame-pointer`、调
试信息级别、profile/coverage/PGO 等）一处采纳，免得每个 BUILD 都得显式
带。coverage、profile-generate/use 等从 `command_line.options` 流到此
处。

## 3. Per-target flag 与 include 路径合成

对每个 cc target，`cc_targets.py` 合成 per-edge 变量，由全局 rule 模板展
开：

- **CPP flag**：per-target `-D`（来自 `defs` 属性）+ `extra_cppflags` +
  工具链内禀 cppflags。
- **CXX warnings**：拆分成 C / C++ 两份，分别对应 `cc_config.warnings`
  与 `cc_config.cxx_warnings`。
- **Includes**（`-I.../I...`）：per-target `incs`，加上每个传递依赖的
  `export_incs`（`_get_incs_list()` 走 `expanded_deps` 并去重），再加
  上始终存在的 `-I.`（工作区根）与 `-Ibuild_dir`。

`-Ibuild_dir` 让 `#include "proto/foo.pb.h"` 能解析到
`build_release/proto/foo.pb.h`。来自 `gen_rule`/`proto_library` 的生成
头还被收入 `declared_incs` 给包含检查用，但搜索路径侧由这一项
`-Ibuild_dir` 一次性覆盖。

GCC → MSVC flag 映射（`toolchain.py` 里的 `_map_gcc_flags_to_msvc()`）把
常见形态翻译过去（`-std=c++17` → `/std:c++17`、`-O2` → `/O2`、`-g` →
`/Zi`），把 MSVC 没有的（`-W*`、`-pipe`、`-m*`、`-f*`）静默丢弃。`-D`、
`-I` 透传过去并调整语法。这样 `BLADE_ROOT` 一份 `cc_config.cppflags` 列
表就能跨平台通用。

## 4. 链接

每个产出可执行或动态库的 target，blade 给出一条 `link`（binary）或
`solink`（动态库）规则调用。三处细节：

- **`@${out}.rsp` 响应文件**承载 object/库列表，避免超过 OS 命令行长度
  限制。
- **静态 vs 动态依赖顺序** —— `_static_dependencies()` 与
  `_dynamic_dependencies()` 各自走一遍 `expanded_deps`，分成系统库
  （`#dl` 之类）、用户库、`link_all_symbols` 库。后者放在专门位置，让链
  接器不会丢未被引用的符号。
- **平台相关的 whole-archive 语法** —— 在
  `_generate_link_all_symbols_link_flags()` 中一次性选择：
  - GNU ld：`-Wl,--whole-archive <libs> -Wl,--no-whole-archive`。
  - Apple ld64（macOS）：每个归档 `-Wl,-force_load,<lib>`（没有
    whole-archive 对应物）。
  - MSVC link.exe：每个归档 `/WHOLEARCHIVE:<lib>`。
  按 `sys.platform` / `os.name` 切换；这是 cc target 代码唯一需要操心
  跨平台 linker 语法的地方。

目标文件落在 `<target>.objs/<src.cc>.o`（MSVC 是 `.obj`），同目录有给包
含检查用的 `<target>.objs/<src.cc>.incstk`。

## 5. 特殊 target

- **`cc_plugin`** 形如 `cc_library` 但永远输出 shared object —— 是"发布
  产物"形态，刻意不像 library 那样被 `deps` 拉入。前后缀可定制，适配项
  目既有的 plugin 命名习惯。
- **`cc_test`** 是 `cc_binary`，自动注入
  `cc_test_config.gtest_libs` / `gtest_main_libs` 里的 gtest 库；当
  `heap_check=` 设置时再注入 gperftools。
- **CUDA**（`cu_targets.py`）继承 `CcTarget`。新增 `cudacc` rule
  （`nvcc -ccbin`），通过 `-Xcompiler` 路由宿主编译器 flag，并写同形态
  的 `.incstk`，使 CUDA 代码的宿主侧也参与 hdrs check。

## 6. 用户体验优化要点

- **头搜索路径默认是 `-I.` + `-Ibuild_dir` 再叠 per-target。** 这两条默
  认足以解析任何工作区相对的 `#include "pkg/foo.h"`（源）与
  `#include "pkg/foo.pb.h"`（生成）。target 只在少数非工作区相对场景
  （vendor 库自有根）才需要 `incs`/`export_incs`。
- **响应文件常开**回避了平台相关的命令行长度限制，无需每个 OS 加特例。
- **per-vendor 分支集中化。** `cc_is(...)` 与那个 GCC→MSVC 映射函数让
  target 代码保持一种形态；工具链差异集中在 `toolchain.py` 与
  `backend.py` 的 rule 里，便于集中评审。
- **包含栈复用了编译。** 同一次编译的 `-H`（或 `/showIncludes`）输出既
  产出目标文件、又喂给头文件检查，cc target 几乎不为这套检查多付出
  （详见 [hdrs check](hdrs_check.md)）。
- **编译并行随 ninja 默认**，但某些 rule 引用的 `heavy_pool`（depth=1）
  让 blade 能把不擅长高并行的编译串行化，而不必降低整体构建并行度。
