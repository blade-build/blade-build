# 命令行参考

## 基本命令行语法

```bash
blade <subcommand> [options]... [target patterns]...
```

## 子命令

Blade 支持以下子命令：

- `build` —— 构建指定目标
- `test` —— 构建并执行测试
- `clean` —— 清理指定目标
- `dump` —— 导出有用的信息
- `query` —— 查询目标依赖关系
- `run` —— 构建并执行单个可执行目标
- `init` —— 在当前目录创建 `BLADE_ROOT`
- `root` —— 打印工作区根目录

### `blade init`

通过在当前目录创建 `BLADE_ROOT` 文件来初始化一个新的工作区。文件中包含被注释掉的配置块，按需取消注释并编辑即可。

```bash
blade init                       # 默认：C/C++ 配置块
blade init --lang=cc,java        # 包含 C/C++ 和 Java 配置块
blade init --lang=all            # 包含所有支持的语言
blade init --force               # 即使已处于某个工作区内也强制初始化
```

`--lang` 接受逗号分隔的列表：`cc`（即 `c++`）、`java`、`scala`、`go`、`python`、`proto` 或 `all`。

默认情况下，当前目录**位于某个已有 `BLADE_ROOT` 之内（含当前目录自身或任意上级目录）**时 `blade init` 会拒绝执行，因为这会产生嵌套的工作区。加 `--force` 可强制初始化：覆盖当前目录已有的 `BLADE_ROOT`，或在上级工作区之下创建一个嵌套工作区。

## 目标模式语法

目标模式（target pattern）是以空格分隔的一组模式表达式，用于指定构建目标。它在命令行、配置项以及目标属性中均可使用。

### 支持的模式格式

- `path:name` —— 指定路径下的具体目标
- `path:*` —— 指定路径下的所有目标
- `path` —— 等价于 `path:*`
- `path/...` —— 递归匹配指定路径及其所有子目录下的全部目标
- `:name` —— 当前目录下的目标

### 路径解析规则

- **绝对路径：** 以 `//` 开头的路径从工作空间根目录解析
- **直接目标：** 名字部分不含通配符的模式视为直接目标
- **默认行为：** 未指定目标时，Blade 构建当前目录下的所有目标（不包含子目录）
- **空展开：** `...` 作为路径终结符时，即便展开结果为空也不会报错，只要路径存在即可

### 目录搜索行为

- **递归搜索：** Blade 会对 `...` 模式递归搜索 `BUILD` 文件
- **排除机制：** 在目录中放置空的 `.bladeskip` 文件即可将其排除
- **shell 兼容性：** 安装 [ohmyzsh](https://ohmyz.sh/) 后，裸写 `...` 会被展开为 `..\..`，此时请使用 `./...`

## 基于标签的目标过滤

Blade 支持通过 `--tags-filter` 选项基于标签表达式过滤构建目标。每个目标都支持 [tags 属性](build_file.md#tags)。

### 过滤表达式语法

- **标签名：** 使用完整标签名，如 `lang:cc`、`type:test`
- **逻辑运算符：** `not`、`and`、`or`
- **组选择：** `group:name1,name2` 用于选择同组的多个标签，等价于 `(group:name1 or group:name2)`
- **复合表达式：** 含空格的表达式请使用引号包裹

### 过滤示例

- `--tags-filter='lang:cc'` —— 仅保留 `cc_*` 目标
- `--tags-filter='lang:cc,java'` —— 保留 `cc_*` 与 `java_*` 目标
- `--tags-filter='lang:cc and type:test'` —— 仅保留 `cc_test` 目标
- `--tags-filter='lang:cc and not type:test'` —— 保留 `cc_*` 目标但排除 `cc_test`

### 过滤作用范围

标签过滤只对通过通配符展开的目标生效；直接目标及其依赖不会被过滤。任何被未过滤目标所依赖的目标都会保留在构建列表中，无论其标签是否匹配。

### 查询可用标签

查询当前可用的标签列表：

```console
$ blade dump --all-tags ...
[
   "lang:cc",
   "lang:java",
   "lang:lexyacc",
   "lang:proto",
   "lang:py",
   "type:binary",
   "type:foreign",
   "type:gen_rule",
   "type:library",
   "type:maven",
   "type:prebuilt",
   "type:system",
   "type:test",
   "xxx:xxx"
]
```

## 子命令选项

不同子命令支持不同选项，运行 `blade <subcommand> --help` 可查看完整选项列表。

### 常用命令行选项

- `-m32`、`-m64` —— 目标架构（32 位 / 64 位），默认自动探测
- `-p PROFILE` —— 构建模式（`debug` / `release`），默认为 `release`
- `-k`、`--keep-going` —— 遇到非致命错误时继续执行
- `-j N`、`--jobs=N` —— 并行构建任务数（默认自动并行）
- `-t N`、`--test-jobs=N` —— 并行测试任务数，适用于多 CPU 机器
- `--test-timeout-multiplier=FACTOR` —— 将每个测试的 wall timeout 按 `FACTOR` 放缩（默认 `1.0`）。用于在比基线机器慢的机器（如共享 CI runner）上跑测试，避免按"正常硬件"配置的 `global_config.test_timeout` 太紧导致 false-timeout。仅影响当前 run，不写入配置文件。例：`blade test --test-timeout-multiplier=3 ...`
- `--verbose` —— 显示每条命令的完整命令行
- `-h`、`--help` —— 显示帮助信息
- `--color=yes/no/auto` —— 启用或禁用彩色输出
- `--exclude-targets` —— 加载阶段排除的目标模式（逗号分隔）
- `--generate-dynamic` —— 为每个 `cc_library` 强制生成动态库（`.so` / `.dylib` / `.dll`），即使该库没有被 `dynamic_link` 可执行文件依赖。用于全项目验证动态链接闭合性、或冒烟测试每个库都能动态加载。被单目标 `cc_library(..., generate_dynamic = False)` 覆盖时该库仍保持静态。
- `--cc-check-undefined` —— 本次调用强制启用 [`cc_library` 静态未定义符号检查](build_rules/cc.md#static-undefined-symbol-check)，覆盖 [`cc_library_config.check_undefined`](config.md#cc_library_config) 的项目默认值。单目标 `check_undefined = False` 仍然胜出。
- `--no-cc-check-undefined` —— 本次调用强制禁用静态未定义符号检查。
- `--generate-java` —— 为 `proto_library` 和 `swig_library` 生成 Java 文件
- `--generate-php` —— 为 `proto_library` 和 `swig_library` 生成 PHP 文件
- `--generate-go` —— 为 `proto_library` 生成 Go 文件
- `--gprof` —— 启用 GNU gprof 性能分析。**仅限 Linux**（gcc 与 clang）：`-pg`/gprof 插桩只在 Linux 上有效。macOS 上该标志被静默忽略（Darwin clang 接受 `-pg` 但当作空操作，且没有 gprof 工具 / `gmon.out`），Windows 上 MSVC 根本不认。在这些平台 blade 会跳过该标志并仅警告一次——请改用 `--coverage`，或原生采样分析器（macOS 用 Instruments/`sample`，Linux 用 `perf`）。
- `--coverage` —— 生成代码覆盖率报告（支持 GNU gcov 与 Java jacoco）。C/C++ 在 **gcc 与 clang**（所有平台，含 Windows 上的 **clang-cl**）上走 `--coverage` 的 gcov 插桩，由 gcovr 生成报告。在 Windows 上使用**原生 MSVC `cl.exe`**（没有 gcov 风格插桩）时，blade 改为在运行期用 `Microsoft.CodeCoverage.Console.exe` 采集覆盖率（它通过 PDB 对测试可执行文件做动态插桩——无需编译标志——并输出 Cobertura），再把各测试的报告合并为 `cc_coverage_report/coverage.cobertura.xml`。该工具随 Visual Studio / Build Tools 一起分发；它不支持 ARM64 目标。
- `--profile-generate[=path]` / `--profile-use[=path]` —— [按性能剖析引导优化（PGO）](#按性能剖析引导优化pgo)（gcc、clang 与原生 MSVC）。第一阶段插桩，第二阶段用采集到的 profile 重新构建。
- `--lto[=thin|full|no]` —— [链接期优化（LTO）](#链接期优化lto)（gcc/clang）。为本次构建覆盖项目的 [`cc_config.lto`](config.md#cc_config) 策略：裸 `--lto` = ThinLTO，`--lto=full` = 单体，`--lto=no` = 关闭。即使在 debug 下也生效（逃生口）。

## 链接期优化（LTO）

LTO 在链接期做跨模块优化（内联、去虚化、死代码消除）。一个项目是否带 LTO 发布是一个**稳定决策**，所以主控是项目内禀属性 [`cc_config(lto='thin')`](config.md#cc_config)，这些标志只是逐次覆盖它。

```bash
blade build //foo:server -p release --lto          # 本次构建用 ThinLTO
blade build //foo:server -p release --lto=full     # 单体 LTO
blade build //foo:server -p release --lto=no       # 关闭（开发迭代时跳过 LTO 的链接耗时）
```

- **thin**（`--lto` 的默认）映射到 clang `-flto=thin` / gcc `-flto=auto`；clang 在链接器支持时还会在 `<build_dir>/.cache/thinlto/` 下维护一个持久 ThinLTO 缓存（ld64 / lld / gold 支持；检测到 GNU `bfd` 时省略缓存）。**full** 是单体 `-flto`。
- **仅 release：** debug 构建除非显式给 `--lto`，否则永不启用 LTO。**无独立构建目录**（与 PGO/coverage 不同）—— LTO 会发布且稳定，沿用 `build_release`；开关它会触发一次正常的全量重建。
- **按 target 退出：** 在 `cc_library` 上设 `lto = False` 让它保持 native（作为普通对象与 bitcode 一起链接）——用于在 LTO 下被误编译的 TU，或应保持 native 的库。
- **工具链：** gcc、clang 与**原生 MSVC `cl.exe`**。原生 cl 上 LTO 映射到 `/GL`+`/LTCG`（thin/full 都→`/LTCG`，因为 MSVC LTCG 本就是整程序）；PGO 激活时被吸收（PGO 已做 LTCG）。**`clang-cl` 不在此列**——它的 LLVM-LTO 路径（lld-link + bitcode）作为独立 follow-up。

**工具链说明 / 健壮性。** clang 的 thin 是真正的 ThinLTO（增量、带缓存、支持完善）。gcc 没有 ThinLTO,所以 thin 映射到 gcc 的并行 WHOPR（`-flto=auto`）——另一套模型,没有持久缓存。原生 MSVC 的 `/GL`+`/LTCG` 很稳健,且对象仍是 COFF（故 `cc_check_undefined` 照常工作）。gcc 的整程序 LTO 在**大型 C++ 二进制上也不够健壮**:已观察到 gcc 15.x 在链接重度 protobuf/RPC 二进制时 ICE(`internal compiler error: in odr_types_equivalent_p, at ipa-devirt.cc`)。ICE 是编译器 bug,不是代码错误——遇到时用 `--lto=no` 对那个二进制关掉 LTO(按 TU 的 `lto=False` 救不了,因为失败发生在整程序链接)。一句话:clang ThinLTO 是成熟路径,**gcc 整程序 LTO 当作实验性对待**。运行时收益也依赖工作负载与工具链——集中在真正跨模块的热路径上,其它地方往往可忽略——所以把项目切到 LTO 前,先在你自己的热路径上实测。

## 按性能剖析引导优化（PGO）

PGO(Profile-guided optimization)又称 FDO(feedback-directed optimization) 是指利用程序真实运行过程中采集到的 profile 数据，来指导编译器优化的技术。

PGO 是一个**全局构建模式**（不是 per-target 属性）：先对整个构建插桩，跑一遍代表性负载，再用采集到的 profile 重新构建。目前接入了 **gcc、clang 与原生 MSVC**；两个阶段都使用独立的 `build_*_pgo` 目录，绝不污染普通的 `build_*` 对象。

```bash
# 第一阶段——插桩，然后跑代表性负载采集数据
blade build //foo:server --profile-generate=/tmp/pgo
./build_release_pgo/foo/server   # 充分跑热点路径

# 第二阶段——用 profile 做优化重建
blade build //foo:server --profile-use=/tmp/pgo
```

blade 替你处理的工具链差异：

- **gcc** 直接读 `.gcda` 文件，并加 `-fprofile-correction`（容忍多线程程序的计数偏差）。两阶段**必须**共用构建目录——gcc 按对象文件路径定位 `.gcda`——独立的 `build_*_pgo` 目录正好保证了这一点。
- **clang** 需要一个**已合并的** `.profdata`：插桩运行产出 `.profraw`，而 `-fprofile-use=` 必须指向合并后的文件而非目录。把 `--profile-use` 指向 `.profraw` 所在目录（或已合并的 `.profdata`），**blade 会替你执行 `llvm-profdata merge`**。clang 没有 `-fprofile-correction`，因此不会发出该标志。
- **MSVC** 用的是全程序（LTCG）插桩：blade 用 `/GL` 编译，插桩阶段链接 `/LTCG /GENPROFILE`、优化阶段链接 `/LTCG /USEPROFILE`（静态库用 `lib /LTCG` 归档）。插桩后的程序运行时把 `<binary>!N.pgc` 写在 `<binary>.pgd` 旁边，优化链接时 `/USEPROFILE` 会**自动合并**它们——无需 `pgomgr`。`.pgd` 以输出名为键，因此共用 `build_*_pgo` 目录正是优化阶段能找到插桩阶段 profile 的关键。`path` 参数是 gcc/clang 专用的，MSVC 上无需指定（profile 就在二进制旁边）。

blade 负责构建标志和 clang 的合并步骤；而产出**代表性**负载（以及判断 profile 是否过期）是你的职责。profile **不能**跨编译器复用——插桩、运行、优化都要在同一套工具链上完成。

> **插桩**构建会定义 `BLADE_PGO_GENERATE`（Blade 私有宏，非编译器/业界标准），便于源码在长跑或 fork 型服务里主动刷写 profile —— 例如 `#ifdef BLADE_PGO_GENERATE` → `__llvm_profile_write_file()`（clang）/ `__gcov_dump()`（gcc）/ `PgoAutoSweep(...)`（MSVC）。**优化（use）**构建和 **AutoFDO** 不定义任何宏：这些二进制应当与普通 release 行为完全一致。

### 采样式 PGO（AutoFDO）

上面那套插桩式 PGO 要"插桩构建 → 跑负载 → 优化构建"两遍构建，比较繁琐，且插桩本身有运行开销。

AutoFDO 是 PGO 的**免插桩**形态：不做插桩构建，而是对一个**普通优化**二进制采样，再用结果重建。采集开销约 1%（插桩约 2×），因此 profile 可以直接取自线上真实流量。**gcc/clang**（用 `perf` 采样）和**原生 MSVC**（用 `xperf` 采样——见下面的 SPGO）都支持。使用独立的 `build_*_autofdo` 目录。

```bash
# 第一阶段——带 AutoFDO 友好的调试信息构建，再用 perf 采样
blade build //foo:server --autofdo-generate
perf record -b -- ./build_release_autofdo/foo/server     # -b 开启 LBR 分支记录

# 自己把 perf.data 转成 sample profile（转换需要被采集的二进制）：
#   clang: llvm-profgen --perfdata=perf.data --binary=build_release_autofdo/foo/server --output=foo.prof
#   gcc:   create_gcov  --binary=build_release_autofdo/foo/server --profile=perf.data --gcov=foo.afdo

# 第二阶段——用转换后的 profile 重建
blade build //foo:server --autofdo-use=foo.prof
```

**典型用法——每个版本一次构建（稳态）。** 与插桩式 PGO（总要一个单独的*慢速插桩*构建）不同，AutoFDO 的采集二进制是**普通**二进制,所以一旦有了 profile,就把两个阶段合成**一次既优化又可采集的构建**：

```bash
# 每个版本：用上一轮的 profile 做优化,同时保持可被采样以供下一轮。
blade build //foo:server --autofdo-generate --autofdo-use=foo.prof
# 发布 -> 线上采样 -> 转换 -> 喂给*下一个*版本的 --autofdo-use
```

`--autofdo-generate` 与 `--autofdo-use` 在三套工具链上都能**叠加**（gcc/clang 在 `-fprofile-sample-use`/`-fauto-profile` 之外再加调试信息；MSVC 在 `/spdin:` 之外再链接 `/spgo`——已在 MSVC 14.51、x64 与 ARM64 上验证合法）。于是稳态下每次构建都同时是"用上轮 profile 优化"和"为下轮采集",**没有额外的专门构建**。（第一次先单独跑 `--autofdo-generate` 引导出首个 profile。）AutoFDO 的调试标志开销很小,你也可以把它们固化进 release 配置,日常只传 `--autofdo-use`。

- **clang** → `-fprofile-sample-use=<profile>`；采集构建额外加 `-fdebug-info-for-profiling` + `-funique-internal-linkage-names`（采样到源码的映射更准）。
- **gcc** → `-fauto-profile=<profile>`；采集构建依赖调试行表（上面那两个标志是 clang 专有的）。
- **采集构建会确保有行表。** 采样式 PGO 靠调试行表把采样映射回源码,所以 `--autofdo-generate` 需要它。若 `debug_info_level` 不产生任何调试信息（如 `no`）,Blade 会**仅为本次构建**补上最小行表——`-gmlt`（clang）/ `-g1`（gcc）/ `/Z7`+`/DEBUG`（MSVC SPGO）——并打印一次提示。它**绝不降级**已有的 `-g`（后面的 `-gmlt` 会把完整 `-g` 降成最小行表）,所以普通的 `debug_info_level=mid` 构建仍保留完整调试信息。
- **`--autofdo-use` 接受的是*已转换*的 profile**，不是原始 `perf.data`——转换工具（`llvm-profgen`/`create_gcov`）需要被采集的二进制，而 Blade 在构建时拿不到。传入原始 `perf.data` 会被识别并拒绝，并提示转换命令。
- **原生 MSVC** 用它自己的采样式 PGO —— **SPGO**（[Sample Profile Guided Optimization](https://devblogs.microsoft.com/cppblog/introducing-sample-profile-guided-optimization-in-msvc/)，VS 2022 / 2026，MSVC 14.51+），Blade 用同一组 `--autofdo-*` 标志来驱动它：`--autofdo-generate` 链接 `/spgo`（采集构建），`--autofdo-use=app.spd` 链接 `/LTCG /spdin:app.spd`（两者都编译 `/GL`）。你用 **`xperf`** 采样（任意 CPU 都支持 IP 采样，LBR 需 Intel Haswell+/AMD Zen 4+/ARM64 ARMv9.2-A+）、用 **`SPDConvert`** 转出 `.spd`——这一步和 perf 一样是你的职责。**clang-cl** 在 Windows 上做不了采样式 PGO（SPGO 是 cl 专有，AutoFDO 又要 `perf`），所以 `--autofdo-*` 在 clang-cl 上会被跳过并警告。

**平台可用性（采集 vs 使用）。** 采样式 PGO 的**采集**需要硬件采样：gcc/clang 需 `perf` + **LBR**（一台**裸机 / 有 PMU 直通的 x86_64 Linux**——ARM Linux 虚拟机通常不暴露 PMU/LBR，`perf record -b` 会失败）；原生 MSVC 需 `xperf`（IP 采样任意 CPU 都行,含 ARM64）。**macOS 则完全没有采样式 PGO 的采集途径**（没有 `perf`,也没有 SPGO；Instruments/`sample`/`dtrace` 都喂不进 `llvm-profgen`）——`--autofdo-use` 的标志仍是可移植的,所以 Linux 上采到的 profile **可以**拿到那里用,但跨 OS/架构复用并不精确、也不受支持。在采集不了的平台上,**请改用插桩式 PGO**（`--profile-generate`/`--profile-use`）——在所有平台上都完全可用、不需要任何特殊硬件。

> **参考：** [GCC AutoFDO 教程](https://gcc.gnu.org/wiki/AutoFDO/Tutorial) · [MSVC SPGO](https://devblogs.microsoft.com/cppblog/introducing-sample-profile-guided-optimization-in-msvc/)

## 使用示例

```bash
# 构建当前目录下的所有目标（不包含子目录）
blade build

# 构建当前目录及其所有子目录下的目标
blade build ...

# 构建当前目录下名为 'urllib' 的特定目标
blade build :urllib

# 构建 'app' 目录下的所有目标，但排除 'sub' 子目录
blade build app... --exclude-targets=app/sub...

# 从工作空间根目录和 common 子目录构建并测试所有目标
blade test //common/...
blade test base/...

# 构建并运行 base 子目录下的特定测试目标
blade test base:string_test
```

## 命令行补全

Blade 在安装后自带基础的命令行补全能力。如需更强大的补全功能，请安装 [argcomplete](https://pypi.org/project/argcomplete/)。

### 安装

```console
pip install argcomplete
```

对于非 root 用户，可加 `--user`：

```console
pip install --user argcomplete
```

### 配置

在 `~/.bashrc` 中加入以下一行：

```bash
eval "$(register-python-argcomplete blade)"
```
