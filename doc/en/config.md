# Configuration System

## Configuration File Hierarchy

Blade employs a multi-level configuration system that loads files in the following precedence order, with each subsequent level overriding the previous:

- **Global Configuration**: `blade.conf` in the Blade installation directory
- **User Configuration**: `~/.bladerc` in the user's home directory
- **Project Configuration**: `BLADE_ROOT` file (also functions as a configuration file)
- **Local Configuration**: `BLADE_ROOT.local` for developer-specific temporary adjustments

## Configuration Syntax

Configuration files use a function-call syntax similar to BUILD files:

```python
global_config(
    test_timeout = 600,
)
```

### Key Characteristics:
- Configuration items can be specified in any order
- Most parameters have sensible defaults that rarely need modification
- Only override settings when specific customization is required

## Configuration Inspection

To examine current configuration settings:

```bash
# Dump configuration to file
blade dump --config --to-file my.config

# Display configuration to stdout
blade dump --config
```

### global_config

Global build system configuration parameters:

#### `backend_builder`: string = "ninja"
**Backend Build System**

Currently supports only `ninja` as the backend build system.

**Technical Background:** Blade previously used SCons but transitioned to [Ninja](https://ninja-build.org/) due to its superior build performance. Ninja is a lower-level build system optimized for speed, making it the exclusive backend choice.

#### `duplicated_source_action`: string = "warning"
**Duplicate Source File Handling**

**Valid Values:** `["warning", "error"]`
**Behavior:** Specifies the action when a source file is detected in multiple targets.

#### `test_timeout`: int = 600
**Test Execution Timeout**

**Unit:** Seconds
**Purpose:** Tests exceeding this duration are automatically marked as failed.

#### `debug_info_level`: string = "mid"
**Debug Information Generation**

**Valid Values:** `["no", "low", "mid", "high"]`
**Trade-off:** Higher levels provide better debugging capability but increase disk space consumption.

#### `build_jobs`: int = 0
**Parallel Build Jobs**

**Range:** 0 to number of CPU cores
**Default Behavior:** 0 enables automatic job count determination by Blade.

#### `test_jobs`: int = 0
**Parallel Test Jobs**

**Range:** 0 to half the number of CPU cores
**Default Behavior:** 0 enables automatic test concurrency management.

#### `test_related_envs`: list = []
**Test-Related Environment Variables**

**Format:** String or regular expression patterns
**Purpose:** Identifies environment variables that impact test behavior during incremental testing.

#### `run_unrepaired_tests`: bool = False
**Unrepaired Test Execution**

**Behavior:** Controls whether to execute tests that failed previously without code changes.

#### `legacy_public_targets`: list = []
**Backward Compatibility for Target Visibility**

**Purpose:** For targets without explicit `visibility` settings, this list determines which targets default to `PUBLIC` visibility.

**Migration Tool:** Use [`tool/collect-missing-visibility.py`](../../tool) to generate this list for existing projects:

```python
global_config(
    legacy_public_targets = load_value('legacy_public_targets.conf')
)
```

#### `default_visibility`: list = []
**Default Target Visibility**

**Valid Values:** `[]` (private) or `['PUBLIC']`
**Historical Context:** Setting to `['PUBLIC']` maintains compatibility with Blade 1.x behavior.

### cc_config

Common configuration parameters for all C/C++ build targets:

#### `extra_incs`: list = []
**Additional Include Directories**

**Purpose:** Specifies extra header file search paths for the compiler.

#### `cppflags`: list = []
**C/C++ Common Compiler Flags**

**Usage:** Flags applicable to both C and C++ compilation.

#### `cflags`: list = []
**C-Specific Compiler Flags**

**Usage:** Flags exclusive to C language compilation.

#### `cxxflags`: list = []
**C++-Specific Compiler Flags**

**Usage:** Flags exclusive to C++ language compilation.

#### `linkflags`: list = []
**Linker Flags**

**Usage:** Additional flags passed to the linker during executable/library linking.

#### `warnings`: list = builtin
**C/C++ Common Warning Flags**

**Default:** `['-Wall', '-Wextra']`
**Recommendation:** The default warning configuration is carefully selected and suitable for most development scenarios.

#### `c_warnings`: list = builtin
**C-Specific Warning Flags**

**Usage:** Warning flags exclusive to C language compilation.

#### `cxx_warnings`: list = builtin
**C++-Specific Warning Flags**

**Usage:** Warning flags exclusive to C++ language compilation.

#### `optimize`: list = ['-O2']
**Optimization Flags**

**Default:** `['-O2']`
**Special Behavior:** Optimization flags are disabled in debug mode to preserve debugging capability.

#### `fission`: bool = False
**Debug Information Fission**

**Feature:** Enables GCC's [DebugFission](https://gcc.gnu.org/wiki/DebugFission) feature.

**Behavior:** When enabled, debug information is separated into `.dwo` files, significantly reducing executable size.

**Performance Impact:** In production testing with medium debug information level, executable size reduced from 1.9GB to 532MB.

**Command Line Alternative:** `--fission` parameter

#### `dwp`: bool = False
**Debug Information Packaging**

**Prerequisite:** Requires `fission = True`

**Function:** Packages scattered `.dwo` files into a single `.dwp` file for easier debug information management and distribution.

**Usage Reference:** See [`cc_binary`](build_rules/cc.md#cc_binary) documentation for `.dwp` file integration.

**Command Line Alternative:** `--dwp` parameter

- `hdr_dep_missing_severity` : string = 'warning' | ['info', 'warning', 'error']

  The severity of the missing dependency on the library to which the header file belongs.

- `hdr_dep_missing_ignore` : dict = {}

  The ignored list when verify missing dependency for a included header file.

  The `hdr_dep_missing_severity` and `hdr_dep_missing_ignore` control the header file dependency
  missing verification behavior. See [`cc_library.hdrs`](build_rules/cc.md#cc_library) for details.

  The format of `hdr_dep_missing_ignore` is a dict like `{ target_label : {src : [headers] }`,
  for example:

  ```python
  {
      'common:rpc' : {'rpc_server.cc':['common/base64.h', 'common/list.h']},
  }
  ```

  Which means, for `common:rpc`, in `rpc_server.cc`, if the libraries which declared `common/base64.h`
  and `common/list.h` are not declared in the `deps`, this error will be ignored.

  For the generated header files, the path can have no build_dir prefix, and it is best not to have it,
  so that it can be used for different build types.

  This feature is to help upgrade old projects that do not properly declare and comply with header
  file dependencies.

  To make the upgrade process easier, for all header missing errors, we provied a [tool](../../tool) to generate
  this information after build.

  ```python
  blade build ...
  path/to/collect-inclusion-errors.py --missing > hdr_dep_missing_suppress.conf
  ```

  So you can copy it to somewhere and load it in you `BLADE_ROOT`:

  ```python
  cc_config(
      hdr_dep_missing_ignore = load_value('hdr_dep_missing_suppress.conf'),
  )
  ```

  In this way, existing header file dependency missing errors will be suppressed, but new ones will be reported normally.

- `allowed_undeclared_hdrs`: list = []

  List of allowed undeclared header files.

  Since the header files in Blade 2 are also included in dependency management, all header files must be explicitly declared.
  But for historical code bases, there will be a large number of undeclared header files, which are difficult to complete in a short time.
  This option allows these header files to be ignored when checking.
  After built, you can also run `tool/collect-inclusion-errors.py` to generate an undeclared headers list file.

  ```python
  blade build ...
  path/to/collect-inclusion-errors.py --undeclared > allowed_undeclared_hdrs.conf
  ```

  And load it:

  ```python
  cc_config(
      allowed_undeclared_hdrs = load_value('allowed_undeclared_hdrs.conf'),
  )
  ```

  Considering the long-term health of the code base, these problems should eventually be corrected.

Example:

```python
cc_config(
    extra_incs = ['thirdparty'], # extra -I, like thirdparty
    warnings = ['-Wall', '-Wextra'...], # C/C++ Public Warning
    c_warnings = ['-Wall', '-Wextra'...], # C special warning
    cxx_warnings = ['-Wall', '-Wextra'...], # C++ Dedicated warning
    optimize = ['-O2'], # optimization level
)
```

### cc_library_config

C/C++ library configuration

- `prebuilt_libpath_pattern` : string = 'lib${bits}'

  The pattern of prebuilt library subdirectory.

  Blade suppor built target for different platforms, such as, under the x64 linux, you can build
  32/64 bit targets with the -m option.

  it also allow some variables which can be substituted:

  - ${bits}  Target bits, such as 32,64.
  - ${arch} Target CPU architecture name, such as i386, x86_64, etc.
  - ${profile} Build mode, can be `debug` or `release`.

  In this way, library files of multiple target platforms can be stored in different subdirectories
  without conflict. This attribute can also be empty string, which means no subdirectory.

  If you only concern to one target platform, it is sure OK to have only one directory or have no
  directory at all.

- `hdrs_missing_severity` : string = 'error' | ['debug', 'info', 'warning', 'error']

  The severity of missing `cc_library.hdrs`

- `hdrs_missing_suppress` : list = []

  List of target labels to be suppressed for above problem.

  Its format is a list of build targets (do not have a'//' at the beginning).

  We also provide an auxiliary tool [`collect-hdrs-missing.py`](../../tool) to easily generate this list.
  If there are too many entries, it is recommended to load them from a separated file:

  ```python
  cc_library_config(
      hdrs_missing_suppress = load_value('blade_hdr_missing_spppress'),
  )
  ```

### cc_test_config

The configuration required to build and run the test:

```python
cc_test_config(
    dynamic_link=True, # Test program default dynamic link, can reduce disk overhead, the default is False
    heap_check='strict', # Open HEAPCHECK of gperftools. For details, please refer to the documentation of gperftools.
    gperftools_libs='//thirdparty/perftools:tcmalloc', # tcmclloc library, blade deps format
    gperftools_debug_libs='//thirdparty/perftools:tcmalloc_debug', # tcmalloc_debug library, blade deps format
    gtest_libs='//thirdparty/gtest:gtest', #gtest library, blade deps format
    gtest_main_libs='//thirdparty/gtest:gtest_main' # gtest_main library path, blade deps format
)
```

Note:

- gtest 1.6 starts, remove install install, but can be bypassed, see
  [gtest1.6.0 installation method](http://blog.csdn.net/chengwenyao18/article/details/7181514).
- The gtest library also relies on pthreads, so gtest_libs needs to be written as `['#gtest', '#pthread']`
- Or include the source code in your source tree, such as thirdparty, you can write
  `gtest_libs='//thirdparty/gtest:gtest'`.

### cuda_config

Common configuration of all cuda targets:

- `cuda_path` : string = ''

  CUDA installed path, it can be empty or starts with "//"

- `cu_warnings` : list = builtin

  CUDA only warnings.

- `cuflags` : list = []

  CUDA common options.

### java_config

Java related configurations:

- `java_home` : string = ''

  Set `$JAVA_HOME`, Take from '$JAVA_HOME' defaultly.

- `version` : string = '' | "8" "1.8", ...

  Provide compatibility with specified release.

- `source_version` : string = ''

  Provide source compatibility with specified release. take value of `version` defaultly.

- `target_version` : string = ''

- `source_encoding` : string = None

  Specify character encoding used by source files.

  Generate class files for specific VM version. take value of `version` defaultly.

- `warnings` : list = ['-Werror', '-Xlint:all']

   Warning flags.

- `fat_jar_conflict_severity` : string = 'warning'

  Severity when fat jar conflict occurs.
  Valid values are: ["debug", "info", "warning", "error"].

- `maven` : string = 'mvn'

  The command to run `mvn`

- `maven_central` : string = ''

  Maven repository URL.

- `maven_jar_allowed_dirs` : list = []

  Directories and subdirectors in which using `maven_jar` is allowed.

  In order to avoid duplication of descriptions of maven artificts with the same id in the code base,
  and version redundancy and conflicts,
  it is recommended to set `maven_jar_allowed_dirs` to prohibit calling `maven_jar` outside these
  directories and their subdirectories.

  Existing `maven_jar` targets that are already outside the allowed directories can be exempted by
  the `maven_jar_allowed_dirs_exempts` configuration item.
  We also provide an auxiliary tool [`collect-disallowed-maven-jars.py`](../../tool) to easily
  generate this list.

  If there are too many entries, it is recommended to load them from a separate file:

  ```python
  java_config(
      maven_jar_allowed_dirs_exempts = load_value('exempted_maven_jars.conf'),
  )
  ```

- `maven_jar_allowed_dirs_exempts` : list []

  Targets which are exempted from the `maven_jar_allowed_dirs` check.

- `maven_snapshot_update_policy` : string = 'daily'

  Update policy of snapshot version in maven repository.

  Valid values of `maven_snapshot_updata_policy` are: "always", "daily"(default), "interval",  "never"
  See [Maven Documents](https://maven.apache.org/ref/3.6.3/maven-settings/settings.html) for details.

- `maven_snapshot_update_interval` : int = 86400

  Update interval of snapshot version in maven repository.

  The unit is minutes.

- `maven_download_concurrency` : int = 0

  Number of processes when download maven artifacts.

  Setting `maven_download_concurrency` to more than `1` can speedup maven artifacts downloading,
  but [maven local repository is not concurrent-safe defaultly](https://issues.apache.org/jira/browse/MNG-2802),
  you can try to install [takari](http://takari.io/book/30-team-maven.html#concurrent-safe-local-repository) to make it safe.
  NOTE there are multiple available versions, the version in the example code of the document is not the latest one.

### proto_library_config

Compile the configuration required by protobuf

```python
proto_library_config(
    protoc='protoc', #protoc compiler path
    protobuf_libs='//thirdparty/protobuf:protobuf', #protobuf library path, Blade deps format
    protobuf_path='thirdparty', # import proto search path, relative to BLADE_ROOT
    protobuf_cc_warning='', # enable warning(disable -w) or not when compiling pb.cc, yes or no
    protobuf_include_path = 'thirdparty', # extra -I path when compiling pb.cc
)
```

### thrift_library_config

Compile the configuration required by thrift

```python
thrift_library_config(
    thrift='thrift', #protoc compiler path
    thrift_libs='//thirdparty/thrift:thrift', #thrift library path, Blade deps format
    thrift_path='thirdparty', # thrift include the search path for the thrift file, as opposed to BLADE_ROOT
    thrift_incs = 'thirdparty', # compile thrift generated .cpp extra -I path
)
```

### Append configuration item values

All configuration items of `list` and `set` types support appending, among which `list` also supports prepending.
The usage is to prefix the configuration item name with `append_` or `prepend_`:

```python
cc_config(
     append_linkflags = ['-fuse-ld=gold'],
     prepend_warnings = ['-Wfloat-compare'],
)
```

For the one configuration item, you cannot assign and append at the same time:

```python
# Wrong!
cc_config(
     linkflags = ['-fuse-ld=gold'],
     append_linkflags = ['-fuse-ld=gold'],
)
```

There was an old `append` form, is deprecated.

```python
cc_config(
    append = config_items(
        Warnings = [...]
    )
)
```

### load_value function

The `load_value` function can be used to load an expression as a value from a file:

```python
cc_config(
    allowed_undeclared_hdrs = load_value('allowed_undeclared_hdrs.conf'),
)
```

The value must conform to the Python literal specification and cannot contain execution statements.

## Environment Variable

Blade also supports the following environment variables:

- `TOOLCHAIN_DIR`, default is empty
- `CPP`, default is `cpp`
- `CXX`, defaults to `g++`
- `CC`, the default is `gcc`
- `LD`, default is `g++`

`TOOLCHAIN_DIR` and `CPP` are combined to form the full path of the calling tool, for example:

Call gcc under `/usr/bin` (original gcc on development machine)

```bash
TOOLCHAIN_DIR=/usr/bin blade
```

Using clang

```bash
CPP='clang -E' CC=clang CXX=clang++ LD=clang++ blade
```

As with all environment variable setting rules, the environment variables placed before the command
line only work for this call. If you want to follow up, use `export`, and put it in `~/.profile`.

Support for environment variables will be removed in the future, instead of configuring the compiler
version, so it is recommended to only use it to test different compilers temporarily.
