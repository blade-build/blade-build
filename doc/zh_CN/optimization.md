# C/C++ 优化（PGO / AutoFDO / LTO）

为 **release** C/C++ 构建榨取更多性能的进阶、可选技术：

- **[按性能剖析引导优化（PGO）](#按性能剖析引导优化pgo)** —— 插桩、跑代表性负载、用采集到的 profile 重建。
- **[采样式 PGO（AutoFDO）](#采样式-pgoautofdo)** —— 免插桩的 PGO：对普通优化二进制采样（线上流量）再重建。
- **[链接期优化（LTO）](#链接期优化lto)** —— 在链接期做跨模块优化（内联、去虚化、死代码消除）。

PGO 与 LTO 是两条独立的轴，可**叠加**（如 `--profile-use` + `--lto`）；AutoFDO 是 PGO 的免插桩形态。相关命令行标志见[命令行参考](command_line.md#子命令选项)；本页讲原理与用法。

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

## 链接期优化（LTO）

LTO 在链接期做跨模块优化（内联、去虚化、死代码消除）。一个项目是否带 LTO 发布是一个**稳定决策**，所以主控是项目内禀属性 [`cc_config(lto='thin')`](config.md#cc_config)，`--lto` 标志只是逐次覆盖它。

```bash
blade build //foo:server -p release --lto          # 本次构建用 ThinLTO
blade build //foo:server -p release --lto=full     # 单体 LTO
blade build //foo:server -p release --lto=no       # 关闭（开发迭代时跳过 LTO 的链接耗时）
```

- **thin**（`--lto` 的默认）映射到 clang `-flto=thin` / gcc `-flto=auto`；clang 在链接器支持时还会在 `<build_dir>/.cache/thinlto/` 下维护一个持久 ThinLTO 缓存（ld64 / lld / gold 支持；检测到 GNU `bfd` 时省略缓存）。**full** 是单体 `-flto`。
- **仅 release：** debug 构建除非显式给 `--lto`，否则永不启用 LTO。**无独立构建目录**（与 PGO/coverage 不同）—— LTO 会发布且稳定，沿用 `build_release`；开关它会触发一次正常的全量重建。
- **按 target 退出：** 在 `cc_library` 上设 `lto = False` 让它保持 native（作为普通对象与 bitcode 一起链接）——用于在 LTO 下被误编译的 TU，或应保持 native 的库。
- **工具链：四种全支持**——gcc、clang、原生 MSVC `cl.exe`、clang-cl。原生 cl 映射到 `/GL`+`/LTCG`（thin/full 都→`/LTCG`，因为 MSVC LTCG 本就是整程序；PGO 激活时被吸收）。**clang-cl** 走 LLVM 路径：`-flto[=thin]`→bitcode，由 `lld-link` 做 LTO（thin 加 `/lldltocache`）。

**工具链说明 / 健壮性。** clang 与 clang-cl 的 thin 是真正的 ThinLTO（增量、带缓存）。gcc 没有 ThinLTO,所以 thin 映射到 gcc 的并行 WHOPR（`-flto=auto`）——另一套模型,没有持久缓存。原生 MSVC 的 `/GL`+`/LTCG` 让对象保持 COFF（故 `cc_check_undefined` 用 `dumpbin` 读取）；clang-cl LTO 产出 bitcode,检查改走 `llvm-nm`——两者都照常工作。gcc 的整程序 LTO 在**大型 C++ 二进制上也不够健壮**:已观察到 gcc 15.x 在链接重度 protobuf/RPC 二进制时 ICE(`internal compiler error: in odr_types_equivalent_p, at ipa-devirt.cc`)。ICE 是编译器 bug,不是代码错误——遇到时用 `--lto=no` 对那个二进制关掉 LTO(按 TU 的 `lto=False` 救不了,因为失败发生在整程序链接)。一句话:clang ThinLTO 是成熟路径,**gcc 整程序 LTO 当作实验性对待**。运行时收益也依赖工作负载与工具链——集中在真正跨模块的热路径上,其它地方往往可忽略——所以把项目切到 LTO 前,先在你自己的热路径上实测。

**自注册 / 插件模式（常见坑）。** LTO 的整程序死代码消除会**删掉那些只在运行期按名字查找的静态初始化注册**——工厂 / 插件 / 依赖注入（DI）注册表，以及一般的自注册对象（`[[gnu::constructor]]` + 注册进 map 的惯用法）。从 LTO 的整程序视角看，注册器无人引用，于是它连同 `Register(...)` 的副作用一起被删除；运行期查找随即失败（`… not found` 或注册表 `CHECK` 失败），尽管**不开 LTO** 时构建与测试都通过。（注意：靠"强制加载归档"的招数——`link_all_symbols` / `-Wl,--whole-archive` / `-Wl,-force_load`——**救不了**：它们只强制把*对象*链接进来，LTO 仍会把注册器内部化并死剥离。LTO 并不为保留符号而尊重 force-load。）这是*代码模式*的性质，不是 blade 或编译器的缺陷；但当项目的 DI 机制用到它时，会一次性挂掉大量测试。

**让注册在 LTO 下存活**的办法是保住注册器——给它加 `[[gnu::used, gnu::retain]]`（`used` 让它躲过 LTO 的 DCE，`retain` 让它躲过链接器的 `--gc-sections`）：

```cpp
[[gnu::constructor, gnu::used, gnu::retain]] static void register_foo() { registry.Register("foo", …); }
```

**`used` + `retain` 仍不够的情形。** 保住注册器，只有在它写入的注册表是**单一实例**时才有用。如果注册表是经由 vague-/COMDAT 链接的单例访问的——例如一个*模板函数内的局部* `static`（`template<class T> T& Get() { static T r; return r; }`）——**ThinLTO 可能把它按 TU 内部化**：注册器跑了，但注册进*它那个* TU 的副本，而查找读的是*另一个*副本 → 仍然 `not found`。这时的修法是把注册表做成**单个强链接的全局**，在单个 `.cc` 里定义（而不是经由模板/inline 局部 static 按 TU 合成）。

**如果无法（或不想）改源码，就对该二进制关掉 LTO** —— 在目标上设 `lto = False`，或用 `--lto=no` 构建。当注册表无法被改造为 LTO-safe 时，这是可靠的解决办法。

无论哪种，发布这类二进制前**务必在 LTO 下跑一遍测试套件**。
