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

#### `toolchain`: str = ""

**Default Toolchain**

**Purpose:** Specifies the default ``cc_toolchain_config`` name to use when
``--cc-toolchain=`` is not given on the command line. The value must match
the ``name`` of a ``cc_toolchain_config()`` entry, or a toolchain kind
(``gcc`` / ``clang`` / ``msvc`` / ``mingw`` / ``cygwin``).

**Override:** ``blade build --cc-toolchain=<name>`` takes precedence.

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

#### `lto`: str = `''` | `'thin'` | `'full'`
**Link-Time Optimization (LTO / ThinLTO)**

The project's LTO policy for **release** builds: `''` (off, default), `'thin'` (ThinLTO — incremental, recommended), or `'full'` (monolithic). A **project intrinsic** (a stable decision that ships, like the optimization level), hence a config item rather than a per-invocation mode. Override per build with `--lto` / `--lto=full` / `--lto=no`, or opt a target out with `lto = False`.

See **[C/C++ Optimization → LTO](optimization.md#link-time-optimization-lto)** for the full story — release-only gating, the per-toolchain mapping (gcc/clang/native-MSVC/clang-cl), the ThinLTO cache, and robustness notes.

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

#### `pie`: str = `'auto'` | `'yes'` | `'no'`
**Executable PIE posture (Linux only)**

blade compiles every translation unit with `-fPIC` so a single object set can serve `.a`, `.so`, and executables (compile once, link many). But blade never touches `-pie` / `-no-pie`, so an executable's PIE-ness is whatever the toolchain links by default — `gcc` on modern distros defaults to `-pie`, older toolchains or those built with `--disable-default-pie` do not. The result: the hardening posture isn't reproducible across machines.

This knob pins it at the link step:

- `'auto'` (default) — unchanged; follow the toolchain default.
- `'yes'` — append `-pie` to the executable `link` rule (guaranteed PIE, full-image ASLR).
- `'no'` — append `-no-pie` (guaranteed `ET_EXEC` — for embedded / special-loader scenarios that need a non-PIE binary).

Only affects the executable `link` rule; shared libraries (`solink`) are unaffected (a `.so` with `-pie` is contradictory and the linker would error). No effect on macOS (executables are PIE by default and `ld64 -no_pie` was removed in recent versions) or MSVC (no PIC/PIE concept).

**Verify:** `file a.out` reports `pie executable` when `pie='yes'`, `ET_EXEC` when `pie='no'`.

#### `no_semantic_interposition`: bool = True
**Recover `-fPIE`-level optimization under `-fPIC` (GCC only)**

Default `True` makes blade pass `-fno-semantic-interposition` to **GCC** under its always-on `-fPIC`. The compiler then references and inlines the current TU's own global symbols directly instead of routing every reference through the GOT — recovering most of the `-fPIE`-level perf without forking the object set (we still need `-fPIC` for `.so` reuse). GCC's [own docs](https://gcc.gnu.org/onlinedocs/gcc/Code-Gen-Options.html) recommend the flag for "serious users"; CPython adopted it for `libpython3.so` (the matching macro is `Py_HAVE_NO_SEMANTIC_INTERPOSITION` — same double negative as ours, on purpose, to mirror the GCC flag name); Fedora ships it as a package default.

**Per-compiler effect:**
- **GCC** — real win; the flag is emitted. Eliminates GOT indirection and re-enables cross-TU inlining for own globals.
- **Clang / Apple Clang** — already non-interposing by default, so blade does **not** emit the flag. (Emitting it would trigger `-Wunused-command-line-argument` on the C++ driver, breaking `-Werror` projects.) Same posture you'd get on GCC with the flag — for free.
- **MSVC** — no concept; nothing emitted.

**What this does NOT affect** (so leave the default alone if you use any of these):

- `LD_PRELOAD`ed malloc replacements: **jemalloc, tcmalloc, mimalloc, gperftools** — these replace libc's `malloc`/`free`/`calloc`/..., which are *extern* to your TU and always go through the PLT. Unaffected.
- Sanitizers in preload mode (ASan, MSan, TSan, UBSan), `libfaketime`, `electric-fence`, `libeatmydata`, `dlsym(RTLD_NEXT, ...)` shims — same logic; targets are libc / runtime symbols, not your app's own symbols.

**When to set `False`** (opt out of the optimization):

- You use a plugin/injection framework (e.g. Frida, in-app function-patching tools) that overrides symbols **defined in your application binary itself**, and you need internal call sites within the same TU to see the override.
- You ship a library that documents its own symbols as user-replaceable (rare — `libpython` does the opposite).
- You are debugging a strange ABI issue and want GCC's conservative default back.

If you're not doing any of the above, leave it at `True` — the population that genuinely needs `False` is small and self-aware.

Behavior change note: this default differs from earlier blade (off by default, then on by default starting this release). Existing GCC-built binaries get a free perf boost; nothing else changes for the common case.

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

- `unused_deps_severity`: string = 'debug' | ['debug', 'info', 'notice', 'warning', 'error']

  Severity of the unused dependency check: a dep declared in `deps` none of whose public headers
  is directly `#include`d by the target. Defaults to `'warning'` (advisory — reported but does not
  fail the build); set to `'error'` to fail the build on a redundant dep, or `'debug'` to silence
  (the check is skipped and the global declaration is not loaded). Advisory by default, like
  Bazel's `unused_deps` tool and Buck2.

  Exempt from the check:
  - libraries declared with an explicit empty `hdrs = []` (no public interface, so there is no
    header that could be used — note this does NOT exempt `proto_library`, which has `.pb.h`; a
    library with `hdrs` unset (`None`) is also NOT exempt — that is the separate
    `cc_library_config.hdrs_missing_severity` warning);
  - deps listed in `unused_deps_suppress`;
  - deps listed in a target's `keep_deps` attribute (see [build_rules/cc.md](build_rules/cc.md#cc_library)).

- `unused_deps_suppress`: dict = {}

  A `{target: [deps]}` map of intentionally-kept deps to exempt from the unused dependency check,
  mainly for incrementally cleaning up an existing code base.

  ```python
  cc_config(
      unused_deps_severity = 'warning',
      unused_deps_suppress = {
          '//app/foo:bar': ['//common/baz:qux'],
      },
  )
  ```

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

- `generate_dynamic` : bool = False

  Whether to generate a dynamic library in addition to the static library.

- `check_undefined` : bool = True **(EXPERIMENTAL)**

  Project-wide default for the [static undefined-symbol check](build_rules/cc.md#static-undefined-symbol-check).
  When True (default), every `cc_library`'s undefined symbols are statically validated against
  its declared `deps` immediately after the archive is built — moving "missing dep" failures
  earlier in the build, with diagnostics that point at the broken library instead of at the
  final binary.

  The check ships on by default but, while still experimental, its findings default to
  `warning` severity (see `check_undefined_severity` below): the build keeps going so any
  edge cases we haven't seen surface as diagnostics rather than CI failures. Flip the severity
  to `error` once the check is clean on your codebase.

  Override per-invocation with `--cc-check-undefined` / `--no-cc-check-undefined`.
  Override per-target with `check_undefined = False` on `cc_library` (lowest setting wins —
  a per-target `False` cannot be re-enabled from CLI or config).

- `check_undefined_severity` : str = `'warning'`

  Severity of an unresolved-symbol finding:
  - `'warning'` (default, experimental setting) — log the finding via `console.warning` and
    let the build continue.
  - `'error'` — fail the build on any finding (the eventual non-experimental default).

  This setting is project-global; per-target behavior is still controlled by
  `check_undefined` / `allow_undefined`.

- `allow_undefined` : list = []

  Project-wide regex allowlist of mangled symbol names permitted to remain undefined by the
  `check_undefined` static check. Each entry is a Python regex matched with `re.fullmatch`
  against the mangled name (what `nm -u` prints). System symbols (libc, libstdc++, weak
  refs) are handled by an internal baseline; this list is for project-specific exceptions
  (e.g. symbols injected by a code generator or supplied by a not-yet-modeled toolchain
  feature). For a narrower per-target allowlist, set `allow_undefined = [r'pattern', …]`
  on the `cc_library` itself.

  ```python
  cc_library_config(
      check_undefined = True,
      allow_undefined = [
          r'__gcov_.*',         # gcov runtime, provided by --coverage at final link
          r'_ZN3foo3barEv',     # known symbol injected by external codegen
      ],
  )
  ```

- `arflags` : list = ['rcs'] **(DEPRECATED)**

  Deprecated — use `deterministic` and/or `thin` instead.
  Platform-specific archive flags (`rcs`/`D`/`T`) are now handled automatically.

- `deterministic` : bool = False

  Generate deterministic (reproducible) static libraries.

  By default, ``ar`` embeds timestamps, UID, GID, and other metadata into the archive,
  so the same source code produces a different checksum on every build — breaking
  build reproducibility and reducing distributed cache (e.g. ccache) hit rates.

  When enabled, each platform eliminates these sources of non-determinism:

  - **Linux:** passes ``D`` to ``ar`` — zeros out timestamps, UID, and GID, keeping only file contents and symbol table
  - **macOS:** uses ``libtool -static`` instead of ``ar`` (Apple's ``ar`` does not support ``D``; ``libtool -static`` is inherently deterministic)
  - **MSVC:** passes ``/Brepro`` to ``lib.exe`` — likewise zeros out timestamps

- `thin` : bool = False

  Generate thin static libraries that store object file paths instead of actual code.
  **Only supported on Linux** (GNU `ar` `T` flag). Emits an error on macOS and a warning on MSVC where thin archives are not supported.

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

- Since gtest 1.6, `make install` was removed but can be bypassed.
- The gtest library also relies on pthreads, so gtest_libs needs to be written as `['#gtest', '#pthread']`
- Or include the source code in your source tree, such as thirdparty, you can write
  `gtest_libs='//thirdparty/gtest:gtest'`.

### coverage_config

Code coverage report configuration (`blade test --coverage`):

```python
coverage_config(
    # Glob patterns of C/C++ sources to drop from the coverage report.
    # `**` matches across directories (blade glob semantics); `*`/`?` do not.
    exclude=['thirdparty/**', '**/*_test.cc'],
)
```

Applies to every C/C++ toolchain: gcc/clang/clang-cl pass these to gcovr
`--exclude` (affecting both the HTML and the XML); native MSVC `cl.exe`
filters the merged Cobertura by source path and recomputes the totals.
Sources under the build directory (generated code, vendored deps) are always
excluded regardless of this setting.

### msvc_config

MSVC-specific configuration, only effective on Windows:

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

#### `target_arch`: string = 'auto'

**Target architecture to build for.**

**Valid values:** `'auto'` (detect from host), `'x64'`, `'x86'`, `'arm64'`, `'arm64ec'`

#### `msvc_version`: string = 'auto'

**MSVC compiler toolset version prefix.**

**Valid values:** `'auto'` (pick the latest available), or a specific MSVC version prefix
such as `'14.44'`, `'14.51'`.

Each Visual Studio release ships a specific range of MSVC toolset versions:

- **VS 2019** (product version 16.x) ships MSVC 14.2x (14.20 – 14.29)
- **VS 2022** (product version 17.x) ships MSVC 14.3x – 14.4x (14.30 – 14.44)
- **VS 2026** (product version 18.x) ships MSVC 14.50+ (starting at 14.50, versioning is
  [decoupled](https://aka.ms/msvc/lifecycle) from Visual Studio starting with this release)

> **Relationship between VS and MSVC version numbers:**
> Prior to VS 2026, the MSVC toolset version is derived from the Visual Studio product
> version: MSVC 14.**XX** where **XX** = 30 + VS minor version.  For example,
> VS 2022 17.14 ships MSVC 14.44 (= 14.30 + 14).  Starting with VS 2026, MSVC
> versioning is independent and ships on its own [six-month cadence](https://aka.ms/msvc/lifecycle).
> The complete mapping is documented at
> [Microsoft C/C++ compiler versioning](https://learn.microsoft.com/en-us/cpp/overview/compiler-versions).

When `msvc_version` is set to a specific prefix (e.g. `'14.44'`), Blade searches
all installed Visual Studio instances and selects the first one that provides a
matching `VC/Tools/MSVC/<version>` directory.  This is useful for pinning a
compatible toolset — for example, NVIDIA CUDA 13.2 officially supports MSVC 14.4x
(VS 2022) but not MSVC 14.5x (VS 2026).

#### `use_clang`: bool = False

**Compile with `clang-cl` instead of `cl`.**

When `True`, the MSVC toolchain compiles with `clang-cl` (LLVM's MSVC-compatible
driver) and links/archives with `lld-link` / `llvm-lib` when present, falling
back to MSVC's `link` / `lib` otherwise. Everything else — the MSVC ABI,
cl-style flags, Windows SDK discovery and the vcpkg `*-windows*` triplet — is
unchanged, so this is a drop-in compiler swap, not a different `kind`.

The LLVM tools are located automatically from the Visual Studio install (its
bundled LLVM under `VC/Tools/Llvm/<host>/bin`, picked for the host
architecture), so no extra path configuration is needed. See [Using clang-cl on
Windows](#using-clang-cl-on-windows).

#### `cppflags`: list = ['/MD', '/EHsc']

**MSVC-specific C/C++ common compiler flags.**

These are appended to the cross-platform `cc_config.cppflags` after filtering.

#### `cflags`: list = []

**MSVC-specific C-only compiler flags.**

#### `cxxflags`: list = ['/std:c++17']

**MSVC-specific C++-only compiler flags.**

#### `linkflags`: list = ['/SUBSYSTEM:CONSOLE']

**MSVC-specific linker flags.**

#### `warnings`: list = ['/W3']

**MSVC warning level flags.**

#### `optimize`: dict

**MSVC optimization flags for Debug and Release builds.**

Default:

```python
{
    'debug': ['/Od'],
    'release': ['/O2'],
}
```

#### `debug_info_levels`: dict

**MSVC debug information flags per level.**

Default:

```python
{
    'no':   [],
    'low':  ['/Zi'],
    'mid':  ['/Zi', '/DEBUG'],
    'high': ['/Zi', '/DEBUG', '/RTC1'],
}
```

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
    protoc_direct_dependencies=False, # pass --direct_dependencies to protoc
    well_known_protos=[], # see note below
)
```

`well_known_protos` is the list of `.proto` files protobuf itself ships
(`google/protobuf/*.proto`) that are whitelisted as imports when
`protoc_direct_dependencies` is on. Left empty (the default), blade
auto-discovers them by globbing `google/protobuf/**/*.proto` under the
protobuf include tree -- resolved from the `protoc` install (including a
`vcpkg#protobuf` protoc) or from `protobuf_incs` -- so the list stays
correct across protobuf versions without hand-maintenance. If no include
tree is resolvable (e.g. a misconfigured provider), a built-in canonical
list is used as a safety net. Set an explicit list only to override
discovery.

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

## C/C++ Toolchain Configuration

The `cc_toolchain_config()` function selects the C/C++ compiler toolchain. You can define multiple named toolchains and select one via the `--cc-toolchain` command-line flag.

### `kind` — toolchain family

`kind` determines the **ToolChain class**, **flag syntax**, **deps style**, and **default target platform**:

| kind     | flag syntax | deps style | default target |
|----------|-------------|------------|----------------|
| `gcc`    | GCC         | `gcc`      | host platform  |
| `clang`  | GCC         | `gcc`      | host platform  |
| `mingw`  | GCC         | `gcc`      | `windows`      |
| `cygwin` | GCC         | `gcc`      | `windows`      |
| `msvc`   | MSVC        | `msvc`     | `windows`      |

`gcc` and `clang` both use the GCC-family toolchain class — they differ only in the compiler binary and detected vendor. `mingw` and `cygwin` are GCC-family toolchains targeting Windows. To compile with `clang-cl` (LLVM's MSVC-compatible driver), keep `kind='msvc'` and set [`msvc_config.use_clang`](#use_clang-bool--false) — it is the same MSVC toolchain with LLVM's tools, not a separate kind.

### `prefix` — install prefix

- **When set**: tools are looked up only under `<prefix>/bin/<tool>` and `<prefix>/<tool>`. PATH is **never** searched.
- **When not set**: tools are resolved via `which()` on PATH, falling back to the bare tool name.

This ensures a configured toolchain always pins to its own installation and won't accidentally pick up a different version from the system PATH.

### Configuration reference

```python
cc_toolchain_config(
    name   = 'gcc-13',      # Optional — used with --cc-toolchain=gcc-13 to select this config
    kind   = 'gcc',         # 'gcc' | 'clang' | 'msvc' | 'mingw' | 'cygwin' (see table above)

    target = 'linux',       # Optional — target platform: 'linux' | 'darwin' | 'windows'
                            # Default: derived from host (mingw/cygwin/msvc always 'windows')

    prefix     = '/opt/gcc-13',   # Optional — install prefix, scopes tool lookup (no PATH search)
    tool_prefix = '',             # Optional — tool name prefix for cross-compilation
                                  # e.g. 'arm-linux-gnueabihf-' → arm-linux-gnueabihf-gcc

    cc     = '/usr/bin/gcc-13',   # Optional — override individual tools
    cxx    = '/usr/bin/g++-13',
    ld     = ...,                 # Optional — derived from kind/target by default
    ar     = ...,

    # MSVC-only (when kind='msvc')
    msvc_version = '14.44',       # 'auto' or MSVC version prefix like '14.44'
    target_arch  = 'x64',         # 'auto' | 'x64' | 'x86' | 'arm64' | 'arm64ec'
)
```

> **MSVC version numbers** refer to the C/C++ compiler toolchain version
> (e.g. `14.44`, `14.38`, `14.28`), not the Visual Studio product year. See
> [Microsoft C++ compiler versions](https://learn.microsoft.com/en-us/cpp/overview/compiler-versions)
> for the full mapping. When set to `'auto'` (the default), the highest installed
> version is used.

### Multiple toolchain configs

Define several toolchains and select at build time:

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
blade build --cc-toolchain=gcc-13    # Select by name
blade build --cc-toolchain=clang     # Select by kind (auto-detect paths)
```

A config without a `name` serves as the default (used when `--cc-toolchain` is not
specified):

```python
cc_toolchain_config(kind='clang')   # default toolchain
```

### Selection priority

1. `--cc-toolchain=` CLI flag (match by name, then by kind)
2. Named or unnamed `cc_toolchain_config()` in BLADE_ROOT
3. Auto-detection from host platform

### Using clang-cl on Windows

`clang-cl` is not a separate `kind` — it is the MSVC toolchain compiled with
LLVM's cl-compatible driver. Keep `kind='msvc'` (or just rely on Windows
auto-detection) and turn it on in `msvc_config`:

```python
msvc_config(use_clang = True)
```

This reuses the whole MSVC path — ABI, cl-style flags, Windows SDK discovery and
the vcpkg `*-windows*` triplet — but compiles with `clang-cl` and links/archives
with `lld-link` / `llvm-lib` when available (falling back to MSVC's `link` /
`lib` otherwise). The LLVM tools are located automatically from the Visual
Studio install (its bundled LLVM under `VC/Tools/Llvm/<host>/bin`, picked for the
host architecture), so no path configuration is needed. `msvc_version` and
`target_arch` apply exactly as for plain MSVC.

### vcpkg_config

Configuration for consuming [vcpkg](https://github.com/microsoft/vcpkg)
packages as `vcpkg#<port>:<lib>` dependencies. See [Using vcpkg
packages](build_rules/vcpkg.md) for the full guide. A single workspace-level section:
vcpkg allows one version and one feature set per package per workspace.

#### `manage`: bool = True

**Purpose:** When `True` (default), Blade runs `vcpkg install` itself into a
hermetic tree under the build directory, using an overlay triplet that
chainloads Blade's compiler. When `False`, Blade only resolves artifacts that
you installed yourself under `<root>/installed/<triplet>`.

#### `packages`: dict = {}

**Purpose:** The whitelist of allowed ports — the single source of truth for
what a `vcpkg#<port>:<lib>` reference may resolve to. Referencing a port that
is not listed is a hard error. Each value is a version string or a dict with
`version` and/or `features` (plus the optional `linkage`, `link_all_symbols`,
`include_prefix`, `cmake_options` keys — see [Per-port
options](build_rules/vcpkg.md#per-port-options)). `linkage` defaults to `'auto'`
(like `cc_library`: static for static-link consumers, shared on demand for
dynamic-link ones):

```python
vcpkg_config(
    packages = {
        'fmt': '10.2.1',
        'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']},
    },
)
```

#### `baseline`: str = ""

**Purpose:** Pins the ports tree to a date or git SHA
(vcpkg.json `builtin-baseline`). Leaving it empty is not reproducible; pin it
for consistent versions.

#### `registries`: list = []

**Purpose:** Optional private vcpkg registries
(vcpkg-configuration.json `registries`).

#### `root`: str = ""

**Purpose:** The vcpkg installation (tool + ports tree). Empty means
`$VCPKG_ROOT`. In managed mode this locates the `vcpkg` tool; in unmanaged mode
it is also the root of the install tree that is read.

#### `triplet`: str = "auto"

**Purpose:** The vcpkg triplet. `auto` derives it from the resolved
`cc_toolchain` (e.g. `x64-linux`, `arm64-osx`, `x64-windows-static`); set an
explicit triplet to override.

#### `install_dir`: str = ".cache/vcpkg"

**Purpose:** The per-workspace install root for managed mode, relative to the
build directory. Cleared by `blade clean`.

#### `binary_cache`: str = "auto"

**Purpose:** The vcpkg binary-cache backend used to reuse compiled packages
across runs and machines. `"auto"` keeps vcpkg's built-in default (a local
cache under the user's cache directory); any other value is passed straight
through to `vcpkg install --binarysource=<value>`, so it accepts the full
[vcpkg binary-caching](https://learn.microsoft.com/vcpkg/users/binarycaching)
source syntax, for example:

```python
vcpkg_config(
    # A shared directory cache (read+write).
    binary_cache = 'files,/path/to/cache,readwrite',
    # ... or a NuGet feed, GitHub Actions cache, x-azblob, x-gcs, etc.
)
```

Set it to `'clear'` to disable caching entirely. Only consulted in managed
mode (`manage = True`).

#### `direct_use_allowed`: list = []

**Purpose:** Governance — the list of source subtrees (e.g. `'thirdparty'` or
`'//thirdparty'`) where a target may depend on a bare `vcpkg#port:lib`
reference directly. The default empty list imposes no restriction. When
non-empty, a `vcpkg#...` dependency is only accepted if the **referring**
target lives within one of the listed subtrees; anywhere else Blade reports an
error. This lets a team funnel all third-party usage through curated wrapper
`cc_library` targets (kept under `thirdparty/`) while business code depends on
those wrappers rather than on vcpkg ports directly.

```python
vcpkg_config(
    # Only BUILD files under thirdparty/ may write `deps = ['vcpkg#fmt:fmt']`.
    direct_use_allowed = ['thirdparty'],
)
```
