# 配置

## 配置文件

Blade 只有一种配置文件格式，但是支持多重配置文件，按以下顺序依次查找和加载，后加载的配置文件里存在的配置项会覆盖
前面已经加载过的配置项：

- `blade.conf` 在安装目录下，这是全局配置。
- `~/.bladerc` 在用户 `HOME` 目录下，这是用户级的配置。
- `BLADE_ROOT` 其实也是个配置文件，写在这里的是项目级配置。
- `BLADE_ROOT.local` 开发者自己的本地配置文件，用于临时调整参数等用途

配置的语法和构建规则一样，也是函数调用，例如：

```python
global_config(
    test_timeout = 600,
)
```

配置项之间没有顺序要求。绝大多数配置项都有合适的默认值，如果不需要覆盖就无需设置。

你可以用 `blade dump` 命令来输出当前的配置，并根据需要修改使用：

```bash
blade dump --config --to-file my.config
```

不加 `--to-file` 选项，则输出到标准输出。

### global_config

全局配置：

- `backend_builder` : string = 'ninja'

  Blade所用的后端构建系统，只支持 `ninja`。

  Blade 一开始依赖 scons 作为后端，但是后来由于优化的需要，发现 ninja 更合适。
  [ninja](https://ninja-build.org/)是一个专注构建速度的底层构建系统，经实测在构建大型项目时，
  用 ninja 速度比 scons 快很多，因此我们淘汰了对 scons 的支持。

- `duplicated_source_action` : string = 'warning' | ['warning', 'error']

  发现同一个源文件属于多个目标时的行为，默认为`warning`，建议设置为`error`。

- `test_timeout` : int = 600

  运行每个测试的超时时间，单位秒，超过超时值依然未结束，视为测试失败。

- `debug_info_level` : string = 'mid' | ['no', 'low', 'mid', 'high']

  生成的构建结果中调试符号的级别，支持四种级别，越高越详细，可执行文件也越大。

- `build_jobs` : int = 0 | 0~CPU核数

  并行构建的最大进程数量，默认会根据机器配置自动计算。

- `test_jobs` : int = 0 | 0~CPU核数/2

  并行测试的最大进程数量，默认会根据机器配置自动计算。

- `test_related_envs` : list = []

  是否影响增量测试的环境变量名。
  支持字符串或正则表达式。

- `run_unrepaired_tests` : bool = False

  增量测试时，是否运行未修复的（先前已经失败且未修改的）测试。

- `legacy_public_targets` : list = []

  对于未显式设置可见性（`visibility`）的目标，默认设置可见性为 `PUBLIC` 的目标列表。

  对于现存的项目，我们提供了 [`tool/collect-missing-visibilty.py`](../../tool) 工具，可以用来生成这个列表。

  可以把这个工具的输出保存到文件中，然后通过 `load_value()` 加载：

  ```python
  global_config(
      legacy_public_targets = load_value('legacy_public_targets.conf')
  )
  ```

- `default_visibility` : list = [] | ['PUBLIC']

  对于未显式设置可见性（`visibility`）的目标，默认设置的可见性属性。只能设置为空（`[]`）或 `['PUBLIC']`。
  如果设置为 `['PUBLIC']`，就和 Blade 1 保持一致。

### cc_config

所有c/c++目标的公共配置：

- `extra_incs` : list = []

  额外的头文件搜索路径，比如['thirdparty']

- `cppflags` : list = []

  C/C++ 公用编译选项，默认值已经够用，通常不需要设置。

- `cflags` : list = []

  C 专用编译选项。

- `cxxflags` : list = []

  C++ 专用编译选项。

- `linkflags` : list = []

  构建库和可执行文件以及测试时公用的链接选项，比如库搜索路径等。

- `warnings` : list = 内置

  C/C++公用警告。一般是 `-W` 开头，比如 `['-Wall', '-Wextra']` 等。内置的警告选项均经过精心挑选，建议保持。
  有些编译器警告仅用于 C 或 C++，应当分别通过下面的两个选项来设置，不要到这里。

- `c_warnings` : list = 内置

  编译 C 代码时的专用警告。

- `cxx_warnings` : list = 内置

  编译C++代码时的专用警告。

- `optimize` : list = 内置

  优化专用选项，debug 模式下会被忽略，比如 `['-O2'，'-omit-frame-pointer'] 等。
  单独分出 optimize 选项是因为这些选项在 debug 模式下需要被忽略。

- `fission` : bool = False

  是否开启 GCC 的 [DebugFission](https://gcc.gnu.org/wiki/DebugFission) 功能。

  开启后，调试信息会被分离到单独的 `.dwo` 文件中。
  这能显著减小可执行文件的大小。经实测，在中等调试符号级别下，能把一个被测可执行文件从 1.9GB 减小到 532MB。

  也可以通过命令行参数 `--fission` 来开启此功能。

- `dwp`: bool = False

  是否将 `.dwo` 文件打包成 `.dwp` 文件。

  此选项需要在开启 `fission` 的基础上使用。开启后，构建过程中会自动将分散的 `.dwo` 调试信息文件
  打包成单个 `.dwp` 文件，便于调试信息的管理和分发。关于如何在 package 中使用 dwp 文件，
  请参见 [`cc_binary`](build_rules/cc.md#cc_binary) 文档。

  也可以通过命令行参数 `--dwp` 来开启此功能。

- `hdr_dep_missing_severity` : string = warning | ['info', 'warning', 'error'

  对头文件所属的库的依赖的缺失的严重性。
  和 `hdr_dep_missing_suppress` 一起控制头文件依赖缺失检查的行为，参见 [`cc_library.hdrs`](build_rules/cc.md#cc_library)。

- `hdr_dep_missing_suppress` : dict = {}

  对头文件所属的库的依赖的缺失检查的抑制列表。

  格式是一个字典，样子是 `{ 目标 : {源文件名 : [头文件列表] }`，例如：

  ```python
  {
      'common:rpc' : {'rpc_server.cc':['common/base64.h', 'common/list.h']},
  }
  ```

  表示对于 `common:rpc`, 在 `rpc_server.cc` 中，如果声明了头文件 `common/base64.h` 和 `common/list.h`
  的库没有出现在其 `deps` 中，这个错误也会被抑制。

  对于生成的头文件，路径没有构建目录前缀（比如 `build64_release`），这样可以适用于不同的构建类型。

  这个功能是为了帮助升级未正确声明和遵守头文件依赖的旧项目。为了让升级更容易，我们还提供了一个[工具](../../tool)，
  可以在构建后方便地生成这样格式的文件。

  ```python
  blade build ...
  path/to/collect-inclusion-errors.py --missing > hdr_dep_missing_suppress.conf
  ```

  因此你可以在把这个文件复制到某处，然后在 `BLADE_ROOT` 中加载:

  ```python
  cc_config(
      hdr_dep_missing_suppress = load_value('hdr_dep_missing_suppress.conf'),
  )
  ```

  这样，现存的头文件依赖缺失错误都会被屏蔽掉，但是新增的则会正常报告出来。

- `allowed_undeclared_hdrs` : list = []

  允许的未声明的头文件的列表。

  由于 Blade 2 中头文件也被纳入了依赖管理，所有的头文件都必须显式地声明。但是对于历史遗留代码库，会有大量的未声明的头文件，
  短期内难以一下子补全。这个选项允许在检查时忽略这些头文件。

  可以在构建后，运行 `tool/collect-inclusion-errors.py` 来生成现存的未声明的头文件的列表文件：

  ```python
  blade build ...
  path/to/collect-inclusion-errors.py --undeclared > allowed_undeclared_hdrs.conf
  ```

  然后加载使用：

  ```python
  cc_config(
      allowed_undeclared_hdrs = load_value('allowed_undeclared_hdrs.conf'),
  )
  ```

  从代码库的长期健康考虑，最终还是应当修正这些问题。

### cc_library_config

C/C++ 库的配置：

- `prebuilt_libpath_pattern` : string = 'lib${bits}'

  预构建的库所在的子目录名的模式。

  Blade 支持生成多个目标平台的目标，比如在 x64 环境下，支持通过命令行参数的 -m 参数编译 32 位和 64 位 目标。
  因此 prebuilt_libpath_pattern 是一个模式，其中包含可替换的变量：

  - ${bits} 目标执行位数，比如 32，64。
  - ${arch} CPU 架构名，比如 i386, x86_64 等。
  - ${profile} 构建模式，`debug` 或者 `release`。

  这样就可以在不同的子目录中同时存放多个目标平台的库文件而不冲突。本属性也可以为空，表示没有子目录
  （库文件就放在当前 BUILD 文件所在的目录）。如果只构建一个平台的目标，可以只有一个目录甚至根本不用子目录。

- `hdrs_missing_severity` : string = 'error' | ['debug', 'info', 'warning', 'error']

  缺少 `cc_library.hdrs` 的严重性。

- `hdrs_missing_suppress` : list = []

  需要抑制缺少 [`cc_library.hdrs`](build_rules/cc.md#cc_library) 问题的目标列表（不要带 `//` 前缀），
  用于抑制现存代码中 hdrs 属性缺少的问题。

  我们还提供了一个辅助工具 [`collect-hdrs-missing.py`](../../tool)方便地生成这个列表。

  如果条目数量太多，建议放在单独的文件中加载：

  ```python
  cc_library_config(
      hdrs_missing_suppress = load_value('blade_hdr_missing_spppress'),
  )
  ```

### cc_test_config

构建和运行测试所需的配置：

- `dynamic_link` : bool = False

  测试程序是否默认动态链接，可以减少磁盘开销。

- `heap_check` : string = ''

  开启 gperftools 的 HEAPCHECK，空表示不开启。

  详情参考 [gperftools](https://gperftools.github.io/gperftools/heap_checker.html)的文档。

- `gperftools_libs` : list = ['#tcmalloc']

  tcmclloc 库，blade deps 格式。

- `gperftools_debug_`libs | list     | ['#tcmalloc_debug']

  tcmalloc_debug 库，blade deps 格式。

- `gtest_libs` : list = ['#gtest']

  gtest 的库，blade deps 格式。

- `gtest_main_libs` : list = [‘#gtest_main’]

  gtest_main 的库路径，blade deps 格式。

注意:

- gtest 1.6 开始，去掉了 make install，但是可以绕过，参见[gtest1.6.0安装方法](http://blog.csdn.net/chengwenyao18/article/details/7181514)。
- gtest 库还依赖 pthread，因此 gtest_libs 需要写成 `['#gtest', '#pthread']`
- 或者把源码纳入你的源码树，比如thirdparty下，就可以写成 `gtest_libs='//thirdparty/gtest:gtest'`。

### cuda_config

所有cuda目标的公共配置：

- `cuda_path` : string = ''

  CUDA 库所在路径, 为空或者 "//" 开头的工作区绝对路径

- `cu_warnings` : list = 内置

  编译 CUDA 代码时的专用警告。

- `cuflags` : list = []

  CUDA 公用编译选项。

### java_config

Java 构建相关的配置：

- `java_home` : string = 读取 '$JAVA_HOME' 环境变量

  设置JAVA_HOME。

- `version` : string = '' | ['8' '1.8'] 等

  JDK 兼容性版本号。默认为空，由编译器决定。

- `source_version` : string = ''

  提供与指定发行版的源代码版本兼容性。默认取 `version` 的值。

- `target_version` : string = ''

  生成特定 VM 版本的类文件。默认取 `version` 的值。

- `warnings` : list = ['-Werror', '-Xlint:all']

  警告设置。

- `source_encoding` : string = None

  设置源代码的默认编码。

- `fat_jar_conflict_severity` : string = 'warning' | ['debug', 'info', 'warning', 'error']

  打包 fat jar 时发生冲突的严重性。

- `maven` : string = 'mvn'

  调用 `mvn` 命令需要的路径。

- `maven_central` : string = ''

  maven 仓库的 URL。

- `maven_jar_allowed_dirs` : list = ''

  允许调用 `maven_jar` 的目录列表（及其子目录）。

  为了避免代码库中对同一个 id 的 maven 制品重复描述以及产生版本冗余和冲突，建议通过设置 `maven_jar_allowed_dirs`
  禁止在这些目录及其子目录外调用 `maven_jar`。

  对于现存的已经散落在期望的目录列表之外的 `maven_jar` 目标，可以通过 `maven_jar_allowed_dirs_exempts` 配置项来豁免。
  我们还提供了一个辅助工具 [`collect-disallowed-maven-jars.py`](../../tool)方便地生成这个列表，如果条目数量太多，
  建议放在单独的文件中加载：

  ```python
  java_config(
      maven_jar_allowed_dirs_exempts = load_value('exempted_maven_jars.conf'),
  )
  ```

- `maven_jar_allowed_dirs_exempts` : list = 空

  豁免 maven_jar_allowed_dirs 检查的目标列表。

- `maven_snapshot_update_policy` : string = 'daily' | ['always', 'daily', 'interval',  'never']

  maven 仓库的 SNAPSHOT 版本的更新策略。

  语义遵守[Maven文档](https://maven.apache.org/ref/3.6.3/maven-settings/settings.html)。

- `maven_snapshot_update_interval` : int = 24 * 60

  maven 仓库的 SNAPSHOT 版本的更新间隔。单位为分钟，默认为一天。

- `maven_download_concurrency` : int = 0

  并发下载 maven_jar 的进程数。

  设置大于 1 的值可以提高下载速度，但是由于[maven 本地仓库缓存默认不是并发安全的](https://issues.apache.org/jira/browse/MNG-2802),
  你可以尝试安装[takari](http://takari.io/book/30-team-maven.html#concurrent-safe-local-repository)
  来确保安全, 注意这个插件其实有多个可用的版本，文档示例里的不是最新的。

### proto_library_config

编译 protobuf 需要的配置：

- `protoc` : string = 'protoc'

  protoc编译器的路径。

- `protobuf_libs` : list =

  protobuf库的路径，Blade deps 格式。

- `protobuf_path` : string =

  import 时的 proto 搜索路径，相对于 BLADE_ROOT。

- `protobuf_cc_warning`: string = ''

  编译pb.cc 时是否开启warnings, yes或者no

- `protobuf_include_path` : string =

  编译 pb.cc 时额外的 -I 路径。

### thrift_library_config

编译thrift需要的配置：

- `thrift` : string = 'thrift'

  thrift 编译器的路径。

- `thrift_libs` : list =

  thrift 库的路径，Blade deps 格式。

- `thrift_incs` : list =

  编译 thrift 生成的 C++ 时额外的头文件搜索路径。

- `thrift_gen_params` : string = 'cpp:include_prefix,pure_enums'

  thrift 的编译参数。

### 追加配置项值

所有 `list` 和 `set` 类型的配置项都支持追加，其中 `list` 还支持在前面添加，用法是在配置项名前
加上 `append_` 或 `prepend_` 前缀：

```python
cc_config(
    append_linkflags = ['-fuse-ld=gold'],
    prepend_warnings = ['-Wfloat-compare'],
)
```

同一个配置项不能同时赋值和追加：

```python
# 错误！
cc_config(
    linkflags = ['-fuse-ld=gold'],
    append_linkflags = ['-fuse-ld=gold'],
)
```

还有一种旧的 `append` 的方法，因为语法繁琐且不支持在前面添加，已废弃：

```python
cc_config(
    append = config_items(
        warnings = [...]
    )
)
```

### load_value 函数

load_value 函数可以用于从指定文件中安全地加载一个值：

```python
cc_config(
    allowed_undeclared_hdrs = load_value('allowed_undeclared_hdrs.conf'),
)
```

值必须符合 Python 字面量规范，不能包含执行语句。

## 环境变量

Blade还支持以下环境变量：

- `TOOLCHAIN_DIR`，默认为空
- `CPP`，默认为 `cpp`
- `CXX`，默认为 `g++`
- `CC`，默认为 `gcc`
- `LD`，默认为 `g++`

`TOOLCHAIN_DIR` 和 `CPP` 等组合起来，构成调用工具的完整路径，例如：

调用 `/usr/bin` 下的 `gcc`（开发机上的原版 `gcc`）

```bash
TOOLCHAIN_DIR=/usr/bin blade
```

使用 `clang`

```bash
CPP='clang -E' CC=clang CXX=clang++ LD=clang++ blade
```

如同所有的环境变量设置规则，放在命令行前的环境变量，只对这一次调用起作用，如果要后续起作用，用 `export`，要持久生效，
放入 `~/.profile` 中。

环境变量的支持将来考虑淘汰，改为配置编译器版本的方式，因此建议仅用于临时测试不同的编译器。
