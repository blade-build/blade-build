# 测试支持

Blade 为测试驱动开发（TDD）提供了完善的支持，支持通过命令行自动执行多个测试程序。

## 增量测试

Blade 的 `test` 子命令默认启用增量测试，以优化测试执行性能。

### 触发重新执行的条件

之前已通过的测试在后续构建中无需再次执行，除非满足以下任一条件：

- **依赖变更：** 测试所依赖的任何目标发生了变化，需要重新生成
- **测试数据变更：** 在 BUILD 文件中通过 `testdata` 属性显式声明的测试数据发生变化
- **环境变量变更：** 相关的环境变量被修改
- **参数变更：** 测试执行参数发生变化
- **测试过期：** 超出了有效期

### 配置选项

- **环境变量：** 通过 `global_config.test_related_envs` 配置与测试相关的环境变量（支持正则表达式）
- **过期时间：** 测试默认有效期为 1 天
- **失败处理：** 失败的测试在下一次会被再执行一次；再次失败后需等构建变化或有效期过期后才会重新运行
- **行为覆盖：** 通过 `global_config.run_unchanged_tests` 或命令行选项 `--run-unchanged-tests` 可覆盖默认行为

## 全量测试

如需无条件执行所有测试，使用 `--full-test` 选项：

```bash
blade test common/... --full-test
```

### always_run 属性

`cc_test` 目标支持 `always_run` 属性，无论增量测试如何判断，都强制执行：

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    always_run = True
)
```

## 并行测试

Blade 支持并行执行测试，以最大化测试效率。

### 配置方式

使用 `-t` 或 `--test-jobs N` 指定并发的测试进程数：

```bash
blade test //common... --test-jobs 8
```

### 互斥执行的测试

`exclusive` 测试会**独占**运行——调度器不会同时运行任何其他测试。两种场景下使用：

1. **相互干扰 / 共享资源。** 测试与其他测试争用固定资源（绑定知名端口、固定磁盘
   路径、系统服务、单例守护进程等），同时运行多个实例会不可靠。
2. **资源过载。** 测试会刻意压满机器（CPU / 内存 / 连接 / fiber 压测，overload 或
   负载测试）。与整套测试并行运行时可能耗尽资源、非确定性地失败或崩溃，尽管它单独
   运行是正确的。

```python
cc_test(
    name = 'zookeeper_test',     # 相互干扰：绑定固定端口
    srcs = 'zookeeper_test.cc',
    exclusive = True
)

cc_test(
    name = 'server_overload_test',   # 过载：压满整台机器
    srcs = 'server_overload_test.cc',
    exclusive = True
)
```

独占测试串行运行，因此应优先修复真正的并发 bug，而不是把测试标为独占；仅在上述两种
情况下使用。

## 测试覆盖率分析

Blade 支持 C++、Java、Scala 测试的覆盖率分析，使用 `--coverage` 选项即可开启。

### C/C++ 覆盖率（gcov + gcovr）

C/C++ 测试覆盖率基于编译器的 [gcov](https://gcc.gnu.org/onlinedocs/gcc/Gcov.html) 插桩（GCC 原生支持，Clang 通过 `llvm-cov gcov`）：

```bash
blade test //foo/... --coverage
```

- 自动加入覆盖率相关的编译/链接选项；测试运行时产生 `.gcno`/`.gcda` 数据。
- 测试结束后，Blade 调用 [gcovr](https://gcovr.com/) 在 `<build_dir>/cc_coverage_report/index.html` 生成可逐级目录下钻（目录 → 文件 → 逐行）的 HTML 报告（并附带 Cobertura 格式的 `coverage.xml`）。请先 `pip install gcovr`；若未安装，Blade 只会告警并跳过报告生成。
- 构建目录下的源文件会被排除，报告只反映你自己的代码，而非生成代码（如 `*.pb.cc`）或第三方依赖（vcpkg 安装在构建目录下）。

### Go 覆盖率（go test -cover）

Go 测试覆盖率基于 Go 内置的 cover 支持：

```bash
blade test //foo/... --coverage
```

- `go_test` 二进制以 `-cover -covermode=count` 编译，并以 `-test.coverprofile` 运行，每个测试产生一份 profile。
- 测试结束后，Blade 合并这些 profile 并调用 `go tool cover -html` 在 `<build_dir>/go_coverage_report/index.html` 生成报告。

### Python 覆盖率（coverage.py）

Python 测试覆盖率基于 [coverage.py](https://coverage.readthedocs.io/)：

```bash
blade test //foo/... --coverage
```

- 每个 `py_test` 在 `coverage run -p` 下运行，各自产生一份数据文件。
- 测试结束后，Blade 合并它们并调用 `coverage html` 在 `<build_dir>/py_coverage_report/index.html` 生成报告。请为测试解释器 `pip install coverage`；若未安装，Blade 只会告警并跳过报告生成。
- 由于测试从打包的 zip 中运行，报告里的文件路径会带有 `.zip/` 前缀。

**独立的构建目录。** `--coverage` 构建的插桩方式与普通构建不同，因此 Blade 为它单独使用一个带 `_coverage` 后缀的兄弟目录——例如 `build64_release_coverage` 而非 `build64_release`。普通构建目录名保持不变，普通构建与覆盖率构建可以并存、互不覆盖、互不触发重新编译，现有工作区与脚本也完全不受影响。

### Java / Scala 覆盖率（JaCoCo）

Java / Scala 测试覆盖率需要配置 JaCoCo：

1. 下载并解压 [JaCoCo](https://www.jacoco.org/jacoco/) 发布包
2. 在 BUILD 文件中配置：

```python
java_test_config(
    ...
    jacoco_home = 'path/to/jacoco',
    ...
)
```

- 覆盖率报告会生成到构建目录下的 `jacoco_coverage_report` 目录
- 若需要行级覆盖率，`global_config.debug_info_level` 需设置为 `mid` 或更高（要求编译时带 `-g:line` 选项）

## Sanitizer（消毒器）

只需一个命令行开关，即可让现有目标树在 sanitizer 下构建并运行，无需改动 BUILD 文件：

```bash
blade test //...                                # 普通
blade test //... --sanitizer=address            # AddressSanitizer（别名：asan）
blade test //... --sanitizer=undefined          # UndefinedBehaviorSanitizer（别名：ubsan）
blade test //... --sanitizer=thread             # ThreadSanitizer（别名：tsan）
blade test //... --sanitizer=address,undefined  # 组合（ASan + UBSan）
```

sanitizer 是**每次运行的选择**（命令行开关），不是项目配置。`--sanitizer` 对 `build`/`run`/`test` 均生效，取值是逗号分隔的**集合**：`address`（`asan`）、`undefined`（`ubsan`）、`leak`（`lsan`）、`thread`（`tsan`）——在 gcc / clang / Apple clang 上支持（MemorySanitizer 后续支持）。集合会被规范化（去重并排序），因此 `--sanitizer=ubsan,address` 与 `--sanitizer=address,undefined` 是同一个构建。运行时不同的 sanitizer 不能组合——`address`/`leak`/`undefined` 可以共存，但 `thread` 与 `address`/`leak` 互斥（非法组合会在启动时明确报错）。

- **编译选项：** 给编译和链接都加上 `-fsanitize=<集合> -fno-omit-frame-pointer -g`（链接以引入 sanitizer 运行时）。UBSan 被设为**致命**（`-fno-sanitize-recover=undefined`），使其发现问题时让测试失败，而非仅打印。对测试，Blade 还会设置合理的 `*_OPTIONS` 默认值（如 `TSAN_OPTIONS=halt_on_error=1`），使检测能可靠地以非零退出——你在环境变量中已设置的值仍然优先。因此 `blade test` 会把检测判为失败。
- **MSVC：** MSVC 工具链**仅**支持 AddressSanitizer——`--sanitizer=address` 用 `/fsanitize=address` 编译（并加 `/Z7` 以便符号化报告），以非增量方式链接（`/INCREMENTAL:NO /DEBUG`；ASan 运行时由编译器自动引入），并把 ASan 运行时 DLL 加入测试的 `PATH`。在 MSVC 上请求其它 sanitizer 会在启动时明确报错。
- **独立的构建目录：** sanitizer 构建与普通构建在 ABI/代码生成上不兼容，因此使用带 sanitizer 标记的独立兄弟目录——`build64_release_asan`。普通的 `build64_release` 不受影响，两者可并存、互不覆盖、互不触发重新编译。
- **按目标退出：** 不应被插桩的目标（有意的 UB、性能热点、对未插桩预编译库的包装）可设置 `sanitize = False`。它仍参与链接（仍获得运行时），只是自身的编译不再插桩。在 MSVC 上同样有效——由于 `cl` 没有 `-fno-sanitize`，Blade 改为将该目标的 `/fsanitize` 标志置空。

```python
cc_library(name = 'crc32_hw', srcs = ['crc32_hw.cc'], sanitize = False)
```

## 测试排除

Blade 支持通过 `--exclude-tests` 参数在批量执行测试时选择性地排除部分测试。

### 使用示例

```bash
blade test base/... --exclude-tests=base/string,base/encoding:hex_test
```

该命令会执行 `base` 目录下的所有测试，但排除 `base/string` 目录下的所有测试，以及具体的 `base/encoding:hex_test` 目标。
