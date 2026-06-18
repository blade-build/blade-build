# 配置系统

## 配置文件层级

Blade 采用多层级配置体系，按以下优先级顺序加载配置文件，后加载的配置会覆盖前面的同名配置项：

- **全局配置：** Blade 安装目录下的 `blade.conf`
- **用户配置：** 用户 HOME 目录下的 `~/.bladerc`
- **项目配置：** `BLADE_ROOT` 文件（它本身也是一个配置文件）
- **本地配置：** `BLADE_ROOT.local`，面向开发者本人的临时调整

## 配置语法

配置文件采用与 BUILD 文件一致的函数调用式语法：

```python
global_config(
    test_timeout = 600,
)
```

### 关键特性

- 配置项之间没有顺序要求
- 绝大多数参数都有合理的默认值，通常无需修改
- 只有确实需要定制时再覆盖

## 查看当前配置

查看当前实际生效的配置：

```bash
# 将配置导出到文件
blade dump --config --to-file my.config

# 将配置打印到标准输出
blade dump --config
```

### global_config

构建系统的全局配置项：

#### `backend_builder`：string = "ninja"

**后端构建系统**

目前仅支持 `ninja` 作为后端构建系统。

**技术背景：** Blade 最初依赖 SCons，后来由于优化的需要切换到了 [Ninja](https://ninja-build.org/)。Ninja 是一个专注于构建速度的底层构建系统，在大型项目中速度显著优于 SCons，因此 Blade 已经完全采用 Ninja 作为唯一后端。

#### `duplicated_source_action`：string = "warning"

**重复源文件的处理策略**

**合法取值：** `["warning", "error"]`
**行为：** 当同一个源文件归属于多个目标时，决定是发出警告还是直接报错。建议设置为 `"error"`。

#### `test_timeout`：int = 600

**测试超时时间**

**单位：** 秒
**用途：** 超过该时间仍未结束的测试会被标记为失败。

#### `debug_info_level`：string = "mid"

**调试信息级别**

**合法取值：** `["no", "low", "mid", "high"]`
**权衡：** 级别越高，调试信息越详细，但磁盘占用也越大。

#### `build_jobs`：int = 0

**并行构建任务数**

**取值范围：** 0 到 CPU 核数
**默认行为：** 设为 0 时，由 Blade 根据机器配置自动决定。

#### `test_jobs`：int = 0

**并行测试任务数**

**取值范围：** 0 到 CPU 核数 / 2
**默认行为：** 设为 0 时，由 Blade 自动决定并发度。

#### `test_related_envs`：list = []

**与测试相关的环境变量**

**格式：** 字符串或正则表达式
**用途：** 指定哪些环境变量会影响增量测试的结果判定。

#### `run_unrepaired_tests`：bool = False

**是否重跑「未修复」的测试**

**行为：** 控制在增量测试中是否重新运行「之前失败、代码仍未修改」的测试。也可通过命令行选项 `--run-unrepaired-tests` 开启。

#### `legacy_public_targets`：list = []

**目标可见性的向后兼容配置**

**用途：** 对于未显式设置 `visibility` 的目标，该列表中列出的目标默认可见性为 `PUBLIC`。

**迁移工具：** 对于存量项目，可使用 [`tool/collect-missing-visibility.py`](../../tool) 生成该列表：

```python
global_config(
    legacy_public_targets = load_value('legacy_public_targets.conf')
)
```

#### `default_visibility`：list = []

**默认的目标可见性**

**合法取值：** `[]`（私有）或 `['PUBLIC']`
**历史背景：** 设置为 `['PUBLIC']` 可保持与 Blade 1.x 的行为一致。

### cc_config

所有 C/C++ 构建目标的公共配置：

#### `toolchain`：str = ""

**默认工具链**

**用途：** 指定命令行未提供 ``--cc-toolchain=`` 时使用的默认
``cc_toolchain_config`` 名称。值必须匹配某个 ``cc_toolchain_config()``
的 ``name``，或者是一种工具链种类（``gcc`` / ``clang`` / ``msvc`` /
``mingw`` / ``cygwin``）。

**覆盖：** ``blade build --cc-toolchain=<name>`` 优先级更高。

#### `extra_incs`：list = []

**额外的头文件搜索路径**

**用途：** 为编译器指定额外的头文件查找目录，例如 `['thirdparty']`。

#### `cppflags`：list = []

**C/C++ 公共编译选项**

**用途：** 同时作用于 C 与 C++ 的编译选项。

#### `cflags`：list = []

**C 专用编译选项**

**用途：** 只在编译 C 代码时生效的选项。

#### `cxxflags`：list = []

**C++ 专用编译选项**

**用途：** 只在编译 C++ 代码时生效的选项。

#### `linkflags`：list = []

**链接选项**

**用途：** 可执行文件与库的链接阶段所使用的附加选项，例如库搜索路径。

#### `warnings`：list = 内置

**C/C++ 公共警告选项**

**默认值：** `['-Wall', '-Wextra']`
**建议：** 默认的警告配置经过精心挑选，适用于绝大多数开发场景，建议保持默认。

#### `c_warnings`：list = 内置

**C 专用警告选项**

**用途：** 只在编译 C 代码时生效的警告。

#### `cxx_warnings`：list = 内置

**C++ 专用警告选项**

**用途：** 只在编译 C++ 代码时生效的警告。

#### `optimize`：list = ['-O2']

**优化选项**

**默认值：** `['-O2']`
**特殊行为：** 该选项在 debug 模式下会被忽略，以保留可调试性。

#### `fission`：bool = False

**调试信息分离（DebugFission）**

**功能：** 启用 GCC 的 [DebugFission](https://gcc.gnu.org/wiki/DebugFission) 能力。

**行为：** 开启后，调试信息会被分离到独立的 `.dwo` 文件，可显著减小可执行文件体积。

**实测效果：** 在中等调试信息级别下，某被测可执行文件体积从 1.9 GB 减小到 532 MB。

**命令行等效：** 可使用 `--fission` 参数开启。

#### `dwp`：bool = False

**打包调试信息**

**前置条件：** 需要同时启用 `fission = True`

**功能：** 将分散的 `.dwo` 文件打包为单个 `.dwp` 文件，便于调试信息的管理与分发。

**使用参考：** 关于如何在 package 中使用 `.dwp` 文件，请参见 [`cc_binary`](build_rules/cc.md#cc_binary) 文档。

**命令行等效：** 可使用 `--dwp` 参数开启。

#### `pie`：str = `'auto'` | `'yes'` | `'no'`

**可执行文件的 PIE 选项（仅 Linux）**

blade 编译时统一加 `-fPIC`，让同一组 `.o` 能服务于 `.a`、`.so` 和可执行文件（一次编译、多次链接）。但 blade 从不主动加 `-pie` / `-no-pie`，所以最终可执行文件是否 PIE 取决于工具链默认值——新版 `gcc` 默认 `-pie`，老的或 `--disable-default-pie` 构建的则不是。结果是同一份代码在不同机器上产出的安全 posture 不一致。

本选项在链接时把这件事钉死：

- `'auto'`（默认）—— 不修改，跟随工具链默认值。
- `'yes'` —— 在可执行的 `link` 规则里追加 `-pie`（强制 PIE，保证全镜像 ASLR）。
- `'no'` —— 追加 `-no-pie`（强制 `ET_EXEC`，用于需要非 PIE 二进制的嵌入式/特殊加载器场景）。

仅作用于可执行 `link` 规则；共享库（`solink`）不受影响（`.so` 加 `-pie` 是矛盾的，链接器会报错）。在 macOS（可执行默认 PIE，`ld64 -no_pie` 也在近年版本中移除）和 MSVC（没有 PIC/PIE 概念）上是 no-op。

**验证方式：** `file a.out` 在 `pie='yes'` 时报 `pie executable`，在 `pie='no'` 时报 `ET_EXEC`。

#### `no_semantic_interposition`：bool = True

**在 `-fPIC` 下恢复 `-fPIE` 级别的优化（仅 GCC）**

默认 `True` 让 blade 在 **GCC** 上把 `-fno-semantic-interposition` 加到编译命令。配合 blade 永远启用的 `-fPIC`，编译器能直接引用/内联当前 TU 内的全局符号，避免走 GOT 间接寻址——把 `-fPIE` 级别的性能拿回来，同时保留 `-fPIC` 的"可以进 `.so`"特性。命名沿用 GCC 自家的 flag 名（含一层双重否定，故意保留以和 GCC 一致；CPython 的对应宏 `Py_HAVE_NO_SEMANTIC_INTERPOSITION` 也是相同写法）。[GCC 文档](https://gcc.gnu.org/onlinedocs/gcc/Code-Gen-Options.html) 推荐"serious users"开启；CPython 给 `libpython3.so` 默认开；Fedora 也作为打包默认。

**各编译器的实际效果：**

- **GCC** —— 真实收益；flag 被加入命令。消除自身全局符号的 GOT 间接，恢复跨 TU 内联。
- **Clang / Apple Clang** —— 自身已默认不可插桩，所以 blade **不会**主动加这个 flag。（如果加，C++ driver 会报 `-Wunused-command-line-argument`，开 `-Werror` 的项目编不过。）等同于 GCC 加了 flag 之后的 posture，是免费的。
- **MSVC** —— 没有这个概念；什么都不加。

**不受影响的场景**（用了下列任何一种都可放心保持默认）：

- `LD_PRELOAD` 风格的 malloc 替换：**jemalloc、tcmalloc、mimalloc、gperftools** —— 它们替换的是 libc 的 `malloc`/`free`/`calloc`/...，这些符号是 *extern* 到你的 TU 之外的，永远走 PLT。**不受影响**。
- preload 模式下的 sanitizers (ASan/MSan/TSan/UBSan)、`libfaketime`、`electric-fence`、`libeatmydata`、`dlsym(RTLD_NEXT, ...)` 风格的 shim —— 同理，目标都是 libc / runtime 符号，不是应用自身符号。

**什么时候应该设 `False`**（关掉本项优化）：

- 你的项目用了插件/注入框架（如 Frida、应用内 function patching 工具），需要替换**你应用自己二进制里定义的符号**，且需要同 TU 内的调用点也看到这些替换。
- 你做的是一个文档化了"用户可替换符号"的库（罕见——`libpython` 反而是反过来用本优化的典型）。
- 你在调试某种诡异的 ABI 问题，想要 GCC 的保守默认行为回来。

如果不属于以上任意一类，保持默认 `True` 即可——真正需要 `False` 的人群很小，并且这类项目通常本来就在精细控制编译选项，会自己注意到。

行为变更说明：此默认值与早期版本的 blade 不同（之前是关，本 release 起默认开）。GCC 用户的现有二进制等于免费拿到性能提升；常见场景下其他什么都没变。

#### `hdr_dep_missing_severity`：string = 'warning'

**头文件所属库依赖缺失的严重性**

**合法取值：** `['info', 'warning', 'error']`
**说明：** 与 `hdr_dep_missing_ignore` 一起控制「引用头文件但未声明其所属库依赖」的检查行为，详见 [`cc_library.hdrs`](build_rules/cc.md#cc_library)。

#### `hdr_dep_missing_ignore`：dict = {}

**头文件依赖缺失的忽略列表**

格式为字典：`{ 目标 : { 源文件 : [头文件列表] } }`。例如：

```python
{
    'common:rpc' : {'rpc_server.cc':['common/base64.h', 'common/list.h']},
}
```

表示对于 `common:rpc`，若在 `rpc_server.cc` 中引用了 `common/base64.h` 和 `common/list.h`，即便其所属库未在 `deps` 中声明，也不会报错。

对于构建过程中生成的头文件，路径无需带构建目录前缀（例如 `build64_release`），最好也不要带，以便在不同构建类型下通用。

该功能用于帮助升级未正确声明和遵守头文件依赖的存量项目。为简化升级过程，我们还提供了[辅助工具](../../tool)，可在构建后自动生成此类信息：

```bash
blade build ...
path/to/collect-inclusion-errors.py --missing > hdr_dep_missing_suppress.conf
```

然后在 `BLADE_ROOT` 中加载：

```python
cc_config(
    hdr_dep_missing_ignore = load_value('hdr_dep_missing_suppress.conf'),
)
```

这样，存量的头文件依赖缺失错误会被抑制，但新增的依然会正常报告。

#### `allowed_undeclared_hdrs`：list = []

**允许的未声明头文件列表**

在 Blade 2 中，头文件也被纳入依赖管理，所有头文件都必须显式声明。对于存量代码库，未声明的头文件数量庞大，短期难以彻底清理。该选项允许在检查时忽略这些头文件。

构建完成后，可使用 `tool/collect-inclusion-errors.py` 生成未声明头文件列表：

```bash
blade build ...
path/to/collect-inclusion-errors.py --undeclared > allowed_undeclared_hdrs.conf
```

然后加载：

```python
cc_config(
    allowed_undeclared_hdrs = load_value('allowed_undeclared_hdrs.conf'),
)
```

从代码库长期健康的角度，最终还是应当把这些问题彻底修正。

#### `unused_deps_severity`：string = 'debug'

**未使用依赖检查的严重性**

**用途：** 检查「在 `deps` 中声明、但其任何公开头文件都没有被本目标直接 `#include`」的多余依赖。可取值为 `debug` / `info` / `notice` / `warning` / `error`。默认 `'warning'`（建议性：会提示但不导致构建失败）；设为 `'error'` 可让多余依赖导致构建失败，或设为 `'debug'` 关闭（不产生输出，也不加载全局声明文件）。与 Bazel 的 `unused_deps`、Buck2 一致，默认是建议性的、不强制。

**豁免：** 以下依赖不会被报告——

- 以**显式空 `hdrs = []`** 声明的「无公开接口」库：它没有可被使用的公开头文件，报告它纯属噪音。注意 `proto_library` 因为有 `.pb.h`，**不**在此列，仍会被检查；`hdrs` **未声明（None）** 的库也不在豁免之列——那是 [`cc_library_config.hdrs_missing_severity`](#cc_library_config) 所管的另一类问题。
- 列在 `unused_deps_suppress` 中的依赖；
- 列在目标 `keep_deps` 属性中的依赖（见 [build_rules/cc.md](build_rules/cc.md#cc_library)）。

#### `unused_deps_suppress`：dict = {}

**未使用依赖检查的抑制列表**

**用途：** 形如 `{target: [deps]}` 的映射，把「有意保留」的依赖从未使用依赖检查中豁免，主要用于存量代码库的逐步治理。

```python
cc_config(
    unused_deps_severity = 'warning',
    unused_deps_suppress = {
        '//app/foo:bar': ['//common/baz:qux'],
    },
)
```

示例：

```python
cc_config(
    extra_incs = ['thirdparty'],         # 额外的 -I，比如 thirdparty
    warnings = ['-Wall', '-Wextra'...],  # C/C++ 公共警告
    c_warnings = ['-Wall', '-Wextra'...],# C 专用警告
    cxx_warnings = ['-Wall', '-Wextra'...], # C++ 专用警告
    optimize = ['-O2'],                  # 优化级别
)
```

### cc_library_config

C/C++ 库的配置：

#### `prebuilt_libpath_pattern`：string = 'lib${bits}'

**预编译库子目录模式**

Blade 支持构建多目标平台的产物，例如在 x64 Linux 下，可以通过 `-m` 选项同时构建 32 位和 64 位目标。

该模式支持以下占位符：

- `${bits}`：目标执行位数，如 32、64
- `${arch}`：CPU 架构名，如 i386、x86_64
- `${profile}`：构建模式，`debug` 或 `release`

通过这种方式，多种目标平台的预编译库可以放置在不同子目录中而互不冲突。该属性也可以设置为空字符串，表示不使用子目录。

如果只关心一个目标平台，完全可以只有一个子目录，甚至根本不用子目录。

#### `generate_dynamic`：bool = False

**是否同时生成动态库**

除了生成静态库之外，是否同时生成动态库。

#### `check_undefined`：bool = True **（实验性）**

**[静态未定义符号检查](build_rules/cc.md#static-undefined-symbol-check)的项目级默认开关。**

默认开启时，每个 `cc_library` 在归档完成后立即对其未定义符号进行静态校验，确认其声明的 `deps` 是否真的覆盖了所有用到的符号——把「缺依赖」的失败时机左移、按库给出诊断信息，而不是堆到最终二进制链接才爆出。

检查默认启用，但目前仍属实验阶段，其诊断默认以 **warning** 级别输出（见下方 `check_undefined_severity`）：构建继续进行，未覆盖到的边缘情况以告警形式出现，而非直接打断 CI。在本检查在你的代码库稳定通过后，可将级别切换为 `error`。

覆盖优先级：

- 单次调用：`--cc-check-undefined` / `--no-cc-check-undefined`。
- 单目标：在 `cc_library` 上设 `check_undefined = False`。**最低值胜出**——单目标 `False` 不能被 CLI 或配置重新开启。

#### `check_undefined_severity`：str = `'warning'`

**未解析符号诊断的级别。**

- `'warning'`（默认，实验阶段值）—— 通过 `console.warning` 输出诊断，构建继续。
- `'error'` —— 任何未解析符号都判定构建失败（脱离实验阶段后的默认目标）。

本配置作用于项目全局；单目标层面的开关仍由 `check_undefined` / `allow_undefined` 控制。

#### `allow_undefined`：list = []

**项目级正则白名单**：列出允许保留为未定义状态的 mangled 符号名（按 `nm -u` 的输出，用 `re.fullmatch` 匹配）。

系统符号（libc、libstdc++、弱引用）由内置基线处理，本清单仅用于项目级别的例外（例如代码生成器注入的符号、或者尚未建模的工具链特性提供的符号）。若只需在某个库内放行，可在 `cc_library` 上直接设 `allow_undefined = [r'pattern', …]`。

```python
cc_library_config(
    check_undefined = True,
    allow_undefined = [
        r'__gcov_.*',         # gcov 运行时，由最终链接的 --coverage 提供
        r'_ZN3foo3barEv',     # 已知由外部 codegen 注入的符号
    ],
)
```

#### `deterministic`：bool = False

**生成可重复构建（deterministic）的静态库。**

默认情况下，`ar` 在打包 `.o` 文件时会嵌入文件的时间戳、UID、GID 等元数据，
导致同一份源码每次构建产物的 checksum 不同，破坏构建的可重复性（reproducible builds），
也让分布式缓存（如 ccache）命中率下降。

启用此选项后，各平台通过以下方式消除不确定性，确保相同源码产生相同的二进制产物：

- **Linux：** 为 `ar` 加上 `D` 标志，清零时间戳、UID、GID，只保留文件内容和符号表
- **macOS：** 使用 `libtool -static` 取代 `ar`（Apple 的 `ar` 不支持 `D` 标志，`libtool -static` 天生是 deterministic 的）
- **MSVC：** 为 `lib.exe` 加上 `/Brepro` 标志，同样清零时间戳

#### `thin`：bool = False

**生成 thin 静态库**，只记录 `.o` 文件路径，不打包实际内容。
**仅 Linux 支持**（GNU `ar` 的 `T` 标志）。macOS 会报错，MSVC 会警告。

#### `arflags`：list = ['rcs'] ~~**（已废弃）**~~

已废弃 — 请改用 `deterministic` 和/或 `thin`。
平台特定的归档标志（`rcs`/`D`/`T`）现在由系统自动处理。

#### `hdrs_missing_severity`：string = 'error'

**缺失 `cc_library.hdrs` 时的严重性**

**合法取值：** `['debug', 'info', 'warning', 'error']`

#### `hdrs_missing_suppress`：list = []

**`hdrs` 缺失检查的抑制列表**

格式为目标列表（不带 `//` 前缀），用于抑制存量代码中的 `hdrs` 属性缺失问题。

我们提供了辅助工具 [`collect-hdrs-missing.py`](../../tool) 用于生成该列表。条目过多时建议独立保存、集中加载：

```python
cc_library_config(
    hdrs_missing_suppress = load_value('blade_hdr_missing_spppress'),
)
```

### cc_test_config

构建和运行测试所需的配置：

```python
cc_test_config(
    dynamic_link = True,  # 测试程序默认动态链接，可减少磁盘占用，默认值为 False
    heap_check = 'strict', # 开启 gperftools 的 HEAPCHECK，详见 gperftools 文档
    gperftools_libs = '//thirdparty/perftools:tcmalloc',           # tcmalloc 库，Blade deps 格式
    gperftools_debug_libs = '//thirdparty/perftools:tcmalloc_debug', # tcmalloc_debug 库
    gtest_libs = '//thirdparty/gtest:gtest',       # gtest 库
    gtest_main_libs = '//thirdparty/gtest:gtest_main' # gtest_main 库
)
```

注意：

- 从 gtest 1.6 起移除了 `make install`，但可以绕过。
- gtest 库还依赖 pthread，因此 `gtest_libs` 可以写成 `['#gtest', '#pthread']`。
- 也可以将源码纳入自己的源码树（如 `thirdparty` 目录），然后写作 `gtest_libs='//thirdparty/gtest:gtest'`。

### msvc_config

MSVC 专有配置，仅在 Windows 下生效：

```python
msvc_config(
    target_arch = 'x64',
    msvc_version = 'auto',
    use_clang = False,
    cppflags = ['/MD', '/EHsc'],
    cxxflags = ['/std:c++17'],
    linkflags = ['/SUBSYSTEM:CONSOLE'],
    warnings = ['/W3'],
)
```

#### `target_arch`：string = 'auto'

**目标架构**

**合法取值：** `'auto'`（自动检测宿主机架构）、`'x64'`、`'x86'`、`'arm64'`、`'arm64ec'`

#### `msvc_version`：string = 'auto'

**MSVC 编译器工具集版本前缀**

**合法取值：** `'auto'`（自动选取最新版本），或指定 MSVC 版本号前缀，如 `'14.44'`、`'14.51'`。

各 Visual Studio 版本与 MSVC 工具集的对应关系：

- **VS 2019**（产品版本 16.x）搭载 MSVC 14.2x（14.20 – 14.29）
- **VS 2022**（产品版本 17.x）搭载 MSVC 14.3x – 14.4x（14.30 – 14.44）
- **VS 2026**（产品版本 18.x）搭载 MSVC 14.50+（从 14.50 开始，MSVC 版本与 VS 产品版本
  [解耦](https://aka.ms/msvc/lifecycle)，按独立的半年周期发布）

> **VS 与 MSVC 版本号的对应关系：**
> 在 VS 2026 之前，MSVC 工具集版本由 VS 产品版本派生：MSVC 14.**XX**，其中
> **XX** = 30 + VS 次要版本号。例如 VS 2022 17.14 搭载 MSVC 14.44（= 14.30 + 14）。
> 从 VS 2026 开始，MSVC 版本独立发布，遵循[半年发布周期](https://aka.ms/msvc/lifecycle)。
> 完整的对应关系参见 Microsoft 官方文档
> [Microsoft C/C++ 编译器版本管理](https://learn.microsoft.com/en-us/cpp/overview/compiler-versions)。

当 `msvc_version` 设置为特定前缀（如 `'14.44'`）时，Blade 会枚举所有已安装的 Visual Studio
实例，选择首个 `VC/Tools/MSVC/<version>` 目录匹配的版本。这对于锁定兼容的工具集非常有用——
例如 NVIDIA CUDA 13.2 官方支持 MSVC 14.4x（VS 2022），但不支持 MSVC 14.5x（VS 2026）。

#### `use_clang`：bool = False

**使用 `clang-cl` 而非 `cl` 进行编译**

设为 `True` 时，MSVC 工具链改用 `clang-cl`（LLVM 的 MSVC 兼容驱动）编译，并在可用时用
`lld-link` / `llvm-lib` 链接和打包（否则回退到 MSVC 的 `link` / `lib`）。其余部分——MSVC
ABI、cl 风格选项、Windows SDK 查找以及 vcpkg 的 `*-windows*` triplet——保持不变，因此这只是
替换编译器，并非另一种 `kind`。

LLVM 工具会从 Visual Studio 安装自动定位（其自带的 LLVM，位于 `VC/Tools/Llvm/<host>/bin`，
按宿主机架构选取），无需额外配置路径。参见[在 Windows 上使用 clang-cl](#在-windows-上使用-clang-cl)。

#### `cppflags`：list = ['/MD', '/EHsc']

**MSVC 专有 C/C++ 公共编译选项**

这些选项经过 Flag 过滤后会追加到跨平台的 `cc_config.cppflags` 之后。

#### `cflags`：list = []

**MSVC 专有 C 编译选项**

#### `cxxflags`：list = ['/std:c++17']

**MSVC 专有 C++ 编译选项**

#### `linkflags`：list = ['/SUBSYSTEM:CONSOLE']

**MSVC 专有链接选项**

#### `warnings`：list = ['/W3']

**MSVC 警告级别选项**

#### `optimize`：dict

**MSVC Debug / Release 优化选项**

默认：

```python
{
    'debug': ['/Od'],
    'release': ['/O2'],
}
```

#### `debug_info_levels`：dict

**MSVC 各调试级别的调试信息选项**

默认：

```python
{
    'no':   [],
    'low':  ['/Zi'],
    'mid':  ['/Zi', '/DEBUG'],
    'high': ['/Zi', '/DEBUG', '/RTC1'],
}
```

### cuda_config

所有 CUDA 目标的公共配置：

#### `cuda_path`：string = ''

**CUDA 安装路径**

可以为空，或以 `//` 开头（表示工作区内的绝对路径）。

#### `cu_warnings`：list = 内置

**CUDA 专用警告选项**

#### `cuflags`：list = []

**CUDA 公共编译选项**

### java_config

Java 构建相关的配置：

#### `java_home`：string = ''

**JAVA_HOME 路径**

默认从 `$JAVA_HOME` 环境变量读取。

#### `version`：string = ''

**JDK 兼容性版本**

例如 `"8"`、`"1.8"` 等。

#### `source_version`：string = ''

**源码兼容性版本**

默认取 `version` 的值。

#### `target_version`：string = ''

**目标 VM 版本**

生成特定 VM 版本的 class 文件，默认取 `version` 的值。

#### `source_encoding`：string = None

**源文件编码**

指定源文件所使用的字符编码。

#### `warnings`：list = ['-Werror', '-Xlint:all']

**Java 警告选项**

#### `fat_jar_conflict_severity`：string = 'warning'

**fat jar 冲突的严重性**

**合法取值：** `["debug", "info", "warning", "error"]`

#### `maven`：string = 'mvn'

**Maven 命令**

调用 `mvn` 时使用的命令名或路径。

#### `maven_central`：string = ''

**Maven 仓库 URL**

#### `maven_jar_allowed_dirs`：list = []

**允许调用 `maven_jar` 的目录（及其子目录）**

为避免代码库中重复描述同一 id 的 Maven 制品、以及由此引发的版本冗余与冲突，建议通过 `maven_jar_allowed_dirs` 限制 `maven_jar` 只能在这些目录及其子目录中调用。

对于已经散落在允许目录之外的存量 `maven_jar` 目标，可通过 `maven_jar_allowed_dirs_exempts` 豁免。
我们还提供了辅助工具 [`collect-disallowed-maven-jars.py`](../../tool) 用于生成此列表：

```python
java_config(
    maven_jar_allowed_dirs_exempts = load_value('exempted_maven_jars.conf'),
)
```

#### `maven_jar_allowed_dirs_exempts`：list = []

**豁免 `maven_jar_allowed_dirs` 检查的目标列表**

#### `maven_snapshot_update_policy`：string = 'daily'

**Maven 仓库 SNAPSHOT 更新策略**

**合法取值：** `"always"`、`"daily"`（默认）、`"interval"`、`"never"`
详见 [Maven 文档](https://maven.apache.org/ref/3.6.3/maven-settings/settings.html)。

#### `maven_snapshot_update_interval`：int = 86400

**SNAPSHOT 更新间隔**

**单位：** 分钟

#### `maven_download_concurrency`：int = 0

**Maven 制品下载的并发数**

设置大于 1 可加速下载，但由于 [Maven 本地仓库默认并非并发安全](https://issues.apache.org/jira/browse/MNG-2802)，建议安装 [takari](http://takari.io/book/30-team-maven.html#concurrent-safe-local-repository) 来保证安全。注意该插件有多个版本，文档示例中的并非最新版。

### proto_library_config

编译 protobuf 所需的配置：

```python
proto_library_config(
    protoc = 'protoc',                                   # protoc 编译器路径
    protobuf_libs = '//thirdparty/protobuf:protobuf',    # protobuf 库，Blade deps 格式
    protobuf_path = 'thirdparty',                        # import 时的 proto 搜索路径，相对 BLADE_ROOT
    protobuf_cc_warning = '',                            # 编译 pb.cc 时是否开启 warning，yes 或 no
    protobuf_include_path = 'thirdparty',                # 编译 pb.cc 时额外的 -I 路径
    protoc_direct_dependencies = False,                  # 是否给 protoc 传 --direct_dependencies
    well_known_protos = [],                              # 见下方说明
)
```

`well_known_protos` 是 protobuf 自带的 `.proto` 文件列表
（`google/protobuf/*.proto`），在开启 `protoc_direct_dependencies` 时作为
允许的 import 白名单传给 protoc。留空（默认）时，blade 会在 protobuf 的头
文件目录下用 `google/protobuf/**/*.proto` 通配自动发现——目录从 `protoc`
的安装位置（包括 `vcpkg#protobuf` 的 protoc）或 `protobuf_incs` 解析得到，
从而无需手工维护、并能随 protobuf 版本保持正确。若无法解析到头文件目录
（例如 provider 配置有误），则回退到内置的标准列表作为兜底。只有需要覆盖
自动发现结果时才显式设置该列表。

### thrift_library_config

编译 thrift 所需的配置：

```python
thrift_library_config(
    thrift = 'thrift',                              # thrift 编译器路径
    thrift_libs = '//thirdparty/thrift:thrift',     # thrift 库，Blade deps 格式
    thrift_path = 'thrift',                         # thrift 文件的搜索路径，相对 BLADE_ROOT
    thrift_incs = 'thirdparty',                     # 编译 thrift 生成的 .cpp 时额外的 -I 路径
)
```

### 追加配置项的值

所有 `list` 和 `set` 类型的配置项都支持追加，其中 `list` 还支持在前面插入。用法是在配置项名前加 `append_` 或 `prepend_` 前缀：

```python
cc_config(
    append_linkflags = ['-fuse-ld=gold'],
    prepend_warnings = ['-Wfloat-compare'],
)
```

同一个配置项不能同时直接赋值和追加：

```python
# 错误！
cc_config(
    linkflags = ['-fuse-ld=gold'],
    append_linkflags = ['-fuse-ld=gold'],
)
```

此外还有一种旧的 `append` 写法，已废弃：

```python
cc_config(
    append = config_items(
        warnings = [...]
    )
)
```

### load_value 函数

`load_value` 函数可以从文件中加载一个表达式并作为值使用：

```python
cc_config(
    allowed_undeclared_hdrs = load_value('allowed_undeclared_hdrs.conf'),
)
```

加载的值必须符合 Python 字面量规范，不能包含可执行语句。

## C/C++ 工具链配置

`cc_toolchain_config()` 函数用于选择 C/C++ 编译工具链。支持定义多个命名工具链，并通过 `--cc-toolchain` 命令行参数选择。

### `kind` — 工具链家族

`kind` 决定 **ToolChain 类**、**编译选项风格**、**依赖风格**和**默认目标平台**：

| kind     | 选项风格 | 依赖风格 | 默认目标   |
|----------|----------|----------|------------|
| `gcc`    | GCC      | `gcc`    | 宿主机平台 |
| `clang`  | GCC      | `gcc`    | 宿主机平台 |
| `mingw`  | GCC      | `gcc`    | `windows`  |
| `cygwin` | GCC      | `gcc`    | `windows`  |
| `msvc`   | MSVC     | `msvc`   | `windows`  |

`gcc` 和 `clang` 使用相同的 GCC 家族工具链类，区别仅在于编译器二进制文件和检测到的厂商。`mingw` 和 `cygwin` 是面向 Windows 的 GCC 家族工具链。如需用 `clang-cl`（LLVM 的 MSVC 兼容驱动）编译，保持 `kind='msvc'` 并设置 [`msvc_config.use_clang`](#use_clangbool--false)——它是搭配 LLVM 工具的同一套 MSVC 工具链，并非独立的 kind。

### `prefix` — 安装前缀

- **指定时**：仅在 `<prefix>/bin/<tool>` 和 `<prefix>/<tool>` 下查找工具，**绝不**搜索 PATH。
- **未指定时**：通过 `which()` 在 PATH 中查找，找不到时回退到裸工具名。

这确保已配置的工具链始终固定使用其自带的安装版本，不会意外从系统 PATH 中获取其他版本。

### 配置参考

```python
cc_toolchain_config(
    name   = 'gcc-13',      # 可选 — 配合 --cc-toolchain=gcc-13 选择此配置
    kind   = 'gcc',         # 'gcc' | 'clang' | 'msvc' | 'mingw' | 'cygwin'（参见上表）

    target = 'linux',       # 可选 — 目标平台: 'linux' | 'darwin' | 'windows'
                            # 默认: 由 host 推导 (mingw/cygwin/msvc 始终为 'windows')

    prefix     = '/opt/gcc-13',   # 可选 — 安装前缀，限定工具查找范围（不搜索 PATH）
    tool_prefix = '',             # 可选 — 交叉编译工具名前缀
                                  # 例如 'arm-linux-gnueabihf-' → arm-linux-gnueabihf-gcc

    cc     = '/usr/bin/gcc-13',   # 可选 — 单独覆盖各工具路径
    cxx    = '/usr/bin/g++-13',
    ld     = ...,                 # 可选 — 默认由 kind/target 推导
    ar     = ...,

    # 仅 MSVC (kind='msvc' 时)
    msvc_version = '14.44',       # 'auto' 或 MSVC 版本前缀，如 '14.44'
    target_arch  = 'x64',         # 'auto' | 'x64' | 'x86' | 'arm64' | 'arm64ec'
)
```

> **MSVC 版本号**指的是 C/C++ 编译器工具链版本（如 `14.44`、`14.38`、`14.28`），
> 而非 Visual Studio 产品年份。完整说明参见
> [Microsoft C++ 编译器版本](https://learn.microsoft.com/zh-cn/cpp/overview/compiler-versions)。
> 设为 `'auto'`（默认值）时，自动选择已安装的最高版本。

### 多工具链配置

定义多个工具链，构建时选择：

```python
cc_toolchain_config(
    name   = 'gcc-13',
    kind   = 'gcc',
    prefix = '/opt/gcc-13',
)

cc_toolchain_config(
    name   = 'clang-17',
    kind   = 'clang',
    prefix = '/opt/clang-17',
)
```

```bash
blade build --cc-toolchain=gcc-13    # 按名称选择
blade build --cc-toolchain=clang     # 按类型选择（自动检测路径）
```

不带 `name` 的配置作为默认工具链（未指定 `--cc-toolchain` 时使用）：

```python
cc_toolchain_config(kind='clang')   # 默认工具链
```

### 选择优先级

1. `--cc-toolchain=` 命令行参数（先按名称匹配，再按类型匹配）
2. BLADE_ROOT 中的 `cc_toolchain_config()`（命名或未命名）
3. 宿主机平台自动检测

### 在 Windows 上使用 clang-cl

`clang-cl` 不是独立的 `kind`，而是用 LLVM 的 cl 兼容驱动编译的 MSVC 工具链。保持
`kind='msvc'`（或直接依赖 Windows 自动检测），在 `msvc_config` 中开启即可：

```python
msvc_config(use_clang = True)
```

它完整复用 MSVC 路径——ABI、cl 风格选项、Windows SDK 查找以及 vcpkg 的
`*-windows*` triplet——但用 `clang-cl` 编译，并在可用时用 `lld-link` / `llvm-lib`
链接和打包（否则回退到 MSVC 的 `link` / `lib`）。LLVM 工具会从 Visual Studio
安装自动定位（其自带的 LLVM，位于 `VC/Tools/Llvm/<host>/bin`，按宿主机架构选取），
无需配置路径。`msvc_version` 和 `target_arch` 的用法与普通 MSVC 完全相同。

### vcpkg_config

用于把 [vcpkg](https://github.com/microsoft/vcpkg) 包作为 `vcpkg#<port>:<lib>`
依赖使用的配置。完整说明见[使用 vcpkg 包](build_rules/vcpkg.md)。这是一个工作区级别的单一
节：vcpkg 每个包每个工作区只允许一个版本、一组 features。

#### `manage`: bool = True

**作用：** 为 `True`（默认）时，Blade 自己把 `vcpkg install` 安装到构建目录下的
隔离目录，并使用 chainload 编译器的 overlay triplet。为 `False` 时，Blade 只解析
你自己安装在 `<root>/installed/<triplet>` 下的产物。

#### `packages`: dict = {}

**作用：** 允许的 port 白名单——`vcpkg#<port>:<lib>` 可解析到什么的唯一事实来源。
引用未列出的 port 是硬错误。每个值是版本字符串，或带 `version` 和/或 `features`
的字典（还可带 `linkage`、`link_all_symbols`、`include_prefix`、`cmake_options`
等键，见[单个 port 的选项](build_rules/vcpkg.md#单个-port-的选项)）。`linkage`
默认为 `'auto'`（与 `cc_library` 一致：静态链接消费者用静态库，动态链接消费者按需
用共享库）：

```python
vcpkg_config(
    packages = {
        'fmt': '10.2.1',
        'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']},
    },
)
```

#### `baseline`: str = ""

**作用：** 把 ports 树固定到某个日期或 git SHA（vcpkg.json `builtin-baseline`）。
留空则不可复现；固定它以获得一致的版本。

#### `registries`: list = []

**作用：** 可选的私有 vcpkg registry（vcpkg-configuration.json `registries`）。

#### `root`: str = ""

**作用：** vcpkg 安装位置（工具 + ports 树）。留空表示 `$VCPKG_ROOT`。托管模式下
用于定位 `vcpkg` 工具；非托管模式下同时是被读取的安装树根目录。

#### `triplet`: str = "auto"

**作用：** vcpkg triplet。`auto` 根据解析出的 `cc_toolchain` 推导（如
`x64-linux`、`arm64-osx`、`x64-windows-static`）；指定具体 triplet 可覆盖。

#### `install_dir`: str = ".cache/vcpkg"

**作用：** 托管模式下按工作区的安装根目录，相对于构建目录。`blade clean` 会清除。

#### `binary_cache`: str = "auto"

**作用：** vcpkg 二进制缓存后端，用于跨运行、跨机器复用已编译的包。`"auto"`
保留 vcpkg 内置默认（用户缓存目录下的本地缓存）；其他任何值都会原样传给
`vcpkg install --binarysource=<value>`，因此支持完整的
[vcpkg 二进制缓存](https://learn.microsoft.com/vcpkg/users/binarycaching)源语法，例如：

```python
vcpkg_config(
    # 共享目录缓存（读写）。
    binary_cache = 'files,/path/to/cache,readwrite',
    # ……也可以是 NuGet feed、GitHub Actions 缓存、x-azblob、x-gcs 等。
)
```

设为 `'clear'` 可完全禁用缓存。仅在托管模式（`manage = True`）下生效。

#### `direct_use_allowed`: list = []

**作用：** 治理项——允许直接依赖裸 `vcpkg#port:lib` 引用的源码子树列表（如
`'thirdparty'` 或 `'//thirdparty'`）。默认空列表不施加任何限制。非空时，只有当
**发起依赖的**目标位于列表中某个子树内，`vcpkg#...` 依赖才被接受；否则 Blade 报错。
借此可将所有第三方用法收敛到 `thirdparty/` 下精心维护的包装 `cc_library` 目标，
业务代码只依赖这些包装而非直接依赖 vcpkg port。

```python
vcpkg_config(
    # 仅 thirdparty/ 下的 BUILD 可以写 `deps = ['vcpkg#fmt:fmt']`。
    direct_use_allowed = ['thirdparty'],
)
```
