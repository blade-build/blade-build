# Configuration

## configuration file

Blade supports multiple-level configuration files, which are loaded in the following order.
The loaded configuration will overwrite the previous configuration.

- `blade.conf` in the blade installation directory is the global configuration.
- `~/.bladerc` in the user's `HOME` directory is a user-level configuration.
- `BLADE_ROOT` is also actually a configuration file, put your project-level configuration here.
- `BLADE_ROOT.local` is developer's own local configuration file for temporary adjustment of parameters, etc.

The configuration syntax is similar to the build rules, also through function calls, for example:

```python
global_config(
    test_timeout = 600,
)
```

There is no order requirement between configuration items. Most of the configuration items have appropriate
default values, and there is no need to set them if they do not need to be overwritten.

You can run `blade dump` command to dump current configuration, and modify it as your need:

```bash
blade dump --config --to-file my.config
```

Without the `--to-file` option, the result will be dumped to stdout.

### global_config

Global configuration:

- `backend_builder` : string = "ninja"

  Backend build system, only `ninja` currently.

  [ninja](https://ninja-build.org/) is a lower-level system that focuses on building speeds.
  We used to use scons as the backend, but ninja is much faster, so the we only use ninja as
  backend, and the support for scons is removed.

- `duplicated_source_action` : string = "warning"; ["warning", "error"]

  The action when the same source file is found to belong to multiple targets.

- `test_timeout` : int = 600

  In seconds, tests which can't finish in this seconds will be reported as fail.

- `debug_info_level` : string = "mid" | ["no", "low", "mid", "high"]

  Debug information level, the higher may be helpful for debugging, but cost more disk space.

- `build_jobs` int = 0       | 0~#CPU cores

  The number of concurrent build jobs, 0 means decided by blade itself.

- `test_jobs` : int = 0 | 0~#CPU cores/2

  The number of concurrent test jobs, 0 means decided by blade itself.

- `test_related_envs` : list = []

  string or regex    | Environment variables which will affect tests during incremental test.

- `run_unrepaired_tests` : bool = False

  Whether run unrepaired(no changw after previous failure) tests during incremental test.

- `legacy_public_targets` : list = []

  For targets whose `visibility` is not explicitly set, its visibility is set to `PUBLIC` if it is in this list.

  For existing projects, we provide a too [`tool/collect-missing-visibilty.py`](../../tool), which can be used to generate this list.

  You can save the output of this tool to a file and load it with `load_value()`:

  ```python
  global_config(
      legacy_public_targets = load_value('legacy_public_targets.conf')
  )
  ```

-`default_visibility` : list = [] | ['PUBLIC']

  For targets that do not explicitly set visibility (`visibility`), set it to this value.

  Can only be set to empty (`[]`) or `['PUBLIC']`.
  If set to `['PUBLIC']`, it will be consistent with Blade 1.

### cc_config

Common configuration of all c/c++ targets:

- `extra_incs` : list = []

  header file search paths.

- `cppflags` : list = []

  C/C++ common options.

- `cflags` : list = []

  C only options.

- `cxxflags` : list = []

  C++ only options

- `linkflags` : list = []

  Link options.

- `warnings` : list = builtin

  C/C++ common warnings. such as `['-Wall', '-Wextra']`.

  The default options are carefully handpicked and are recommended to most developers.

- `c_warnings` : list = builtin

  C only warnings.

- `cxx_warnings` : list = builtin

  C++ only warnings.

- `optimize` : list = ['-O2']

  Optimize options. It is separate from other compile flags because it is ignored in debug mode.

- `fission` : bool = False

  Whether to enable GCC's [DebugFission](https://gcc.gnu.org/wiki/DebugFission) feature.

  When enabled, debug information is split into separate `.dwo` files.
  This can significantly reduce the size of executable files. In our real test, with the middle debug information level,
  the size of an executable file has been reduced from 1.9GB to 532MB.

  You can also enable this feature via the command line parameter `--fission`.

- `dwp`: bool = False

  Whether to package `.dwo` files into a `.dwp` file.

  This option requires `fission` to be enabled. When enabled, the build process will automatically package
  the scattered `.dwo` debug information files into a single `.dwp` file, which makes it easier to manage
  and distribute debug information. For how to use dwp files in packages, see the [`cc_binary`](build_rules/cc.md#cc_binary) documentation.

  You can also enable this feature via the command line parameter `--dwp`.

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

  - ${bits}  Target bits, such as 32，64。
  - ${arch} Target CPU architecture name, such as i386, x86_64, etc。
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
