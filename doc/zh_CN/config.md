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

- 从 gtest 1.6 起移除了 `make install`，但可以绕过，参见 [gtest 1.6.0 安装方法](http://blog.csdn.net/chengwenyao18/article/details/7181514)。
- gtest 库还依赖 pthread，因此 `gtest_libs` 可以写成 `['#gtest', '#pthread']`。
- 也可以将源码纳入自己的源码树（如 `thirdparty` 目录），然后写作 `gtest_libs='//thirdparty/gtest:gtest'`。

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
)
```

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

## 环境变量

Blade 还支持以下环境变量：

- `TOOLCHAIN_DIR`：默认为空
- `CPP`：默认为 `cpp`
- `CXX`：默认为 `g++`
- `CC`：默认为 `gcc`
- `LD`：默认为 `g++`

`TOOLCHAIN_DIR` 和 `CPP` 等组合起来，构成调用工具的完整路径。例如：

调用 `/usr/bin` 下的 `gcc`（开发机上的原版 `gcc`）：

```bash
TOOLCHAIN_DIR=/usr/bin blade
```

使用 `clang`：

```bash
CPP='clang -E' CC=clang CXX=clang++ LD=clang++ blade
```

与所有环境变量的规则一致：放在命令行前的环境变量只在本次调用生效；如需持续生效，请使用 `export`，并放入 `~/.profile`。

环境变量支持将来计划逐步淘汰，取而代之的是通过配置显式指定编译器版本，因此建议只在临时测试不同编译器时使用。
