# DSL and API Module

## DSL Language

For more stable build processs, blade's DSL is designed to be a restricted Python language that prohibits some builtin
functions and keywords, include but not limited to:

- `exec`, `execfile` and `eval` To improve the consistency of BUILD files.
- `import` Use the built-in `blade` module instead
- `print` Use the functions in `blade.console` module instead

Some builtin functions are restricted.
- `open` only read mode is allowed

To use some common additional functions, such as `os.path.join`, you need to use similar sub-modules in the `blade` module.
If you want to add more appropriate modules, please make an Issue.

To allow unrestricted python in existing `BUILD` files, set the `global_config.unrestricted_dsl_dirs = [...]`,
to disable DSL restriction globally, set the `global_config.restricted_dsl = False`.

## `blade` Module

The global Blade API module, accessed through `blade.`, includes:

### Config-phase Attributes

These attributes are available in both `BLADE_ROOT` configuration files and BUILD files:

- `host_os` property: Name of the host OS (the machine running the build): `'darwin'`, `'linux'`, or `'windows'`
- `host_arch` property: Canonical host CPU architecture: `'x86_64'`, `'aarch64'`, etc.
- `build_type` property: Current build type: `'debug'` or `'release'`
- `build_type_is_debug()` function: Returns `True` if the build type is `'debug'`
- `console` submodule: Output diagnostic information
- `path` submodule: a Restricted subset of `os.path`
- `re` submodule: The python regex library
- `util` submodule: Auxiliary functions

Note: The build environment (host) is not necessarily the same as the target environment. `host_os` and `host_arch` should primarily be used when invoking host-side developer tools. For platform decisions related to build targets, use `blade.cc_toolchain`'s `target_os` and `target_arch` properties instead.

### BUILD-phase-only Attributes

These attributes are only available during BUILD file loading. Accessing them during `BLADE_ROOT` config parsing will abort with an error. Use [function-valued config items](#function-valued-config-items) to defer evaluation to the BUILD phase:

- `cc_toolchain` object: Read-only proxy to the current platform's C/C++ toolchain
- `config` submodule: Read blade configuration information
- `workspace` submodule: Workspace information
- `current_source_dir` property: The directory where the current BUILD file is located (relative to the root directory of the workspace)
- `current_target_dir` property: The output directory where the current BUILD file is located corresponds to (relative to the root directory of the workspace)

### Config-phase-only Attributes

These attributes are only callable during `BLADE_ROOT` config parsing. Calling them from a BUILD file will abort with an error:

- `getenv(name, default=None)` function: Read an environment variable. See [`blade.getenv`](#bladegetenv) below.
- `set_variable(name, value, override=False)` function: Declare a build variable that BUILD files can read. See [Build Variables](#build-variables) below.

### Both-phase Functions

- `get_variable(name, default=...)` function: Read a build variable declared with `set_variable`. Available in **both** `BLADE_ROOT` and BUILD files. See [Build Variables](#build-variables) below.

---

### `blade.config` Submodule

> **Phase:** BUILD only

Access configuration information, including:

- `get_section()` function: Get the content of a configuration section, such as `cc_config`, which can be read through the `get` method
- `get_item()` function: Get a specific configuration item, such as `blade.config.get_item('cc_config','cppflags')`

### `blade.console` Submodule

Output diagnostic information, including:

- `debug()` function: Output debugging message, which is not displayed by default, only output to the screen after using the `--verbose` option
- `info()` function: Output informational message
- `notice()` function: Output some notiable message
- `warning()` function: Output warning message
- `error()` function: Output error message, which will cause the build to fail

### `blade.path` Submodule

A subset of the `os.path` module, including `abspath()`, `basename()`, `dirname()`, `exists()`, `join()`, `normpath()`, `relpath()`, `sep`, `splitext()`.

### `blade.util` Submodule

Some auxiliary functions, including:

- `var_to_list()` function: If type of the argument is `str`, turn it into `list` contains a single element
- `var_to_list_or_none()` function: Like `var_to_list()`, but passes `None` through unchanged

### `blade.workspace` Submodule

> **Phase:** BUILD only

Get some information about the current [workspace](workspace.md), including:

- `root_dir` property: Returns the directory of the current root workspace
- `build_dir` property: Returns the name of the build subdirectory under the workspace, such as `build_release`

### `blade.getenv`

> **Phase:** `BLADE_ROOT` config only. Calling from a BUILD file aborts with an error.

Read an environment variable from the configuration phase. This is the sanctioned channel for env-driven configuration -- blade does not implicitly read environment variables anywhere else.

```python
def getenv(name: str, default: str | None = None) -> str | None
```

**Typical use:** select a toolchain via a CI matrix without committing the matrix shape into BLADE_ROOT.

```python
# BLADE_ROOT
cc_toolchain_config(
    name = 'default',
    kind = 'gcc',
    cc = blade.getenv('CC', 'gcc'),
    cxx = blade.getenv('CXX', 'g++'),
)
```

Then a CI workflow's `CC=gcc-10 CXX=g++-10 ./blade build ...` selects the right toolchain. Any string-valued config field can be sourced this way.

**Why config-only? Why can't BUILD files (and `.bld` extensions) read the environment at all?** Two reasons, both about keeping builds reproducible:

1. **Auditability.** If any BUILD file could call `getenv`, the set of environment variables that influence the build would be scattered across the whole tree and effectively unknowable. Confining env access to `BLADE_ROOT` keeps every env dependency in one file you can read top-to-bottom.
2. **Hermeticity + correct incrementality.** A BUILD file that silently branches on `$SOMEVAR` produces a different build graph for different developers, and -- worse -- a change to that env var would **not** invalidate the cached per-target build, because the env value never enters the build fingerprint. You would get stale artifacts with no rebuild.

So BUILD files never read the environment directly. To let an env-derived value influence a BUILD file, **fold it into a build variable** in `BLADE_ROOT` and read that variable in BUILD:

```python
# BLADE_ROOT (config phase): read the env once, publish it as a named variable
blade.set_variable('use_jemalloc', blade.getenv('USE_JEMALLOC', '0'))

# any BUILD or *.bld file: read the variable -- never the env
deps = [':core']
if blade.get_variable('use_jemalloc') == '1':
    deps.append('//thirdparty/jemalloc:jemalloc')
```

This keeps the env dependency explicit (one `getenv` in `BLADE_ROOT`) **and** correct for incremental builds: the resolved variable is part of the configuration fingerprint, so a change to `$USE_JEMALLOC` (or a `--define use_jemalloc=1` override) regenerates the affected targets. See [Build Variables](#build-variables). For toolchain fields specifically, you can also read the resolved value from `blade.cc_toolchain.tool('cc')`, which is already env-folded at config time.

### Build Variables

> **Phase:** `set_variable` is `BLADE_ROOT` config only; `get_variable` works in both `BLADE_ROOT` and BUILD/`.bld`.

Build variables are named values that `BLADE_ROOT` publishes and BUILD files read. They are the sanctioned bridge from the environment -- or from any config-time computation -- into otherwise-hermetic BUILD files (which [cannot read the environment](#bladegetenv)).

```python
def set_variable(name: str, value, override: bool = False) -> None   # BLADE_ROOT only
def get_variable(name: str, default = ...)                           # both phases
```

```python
# BLADE_ROOT: declare variables (from env, host info, or plain constants)
blade.set_variable('use_jemalloc', blade.getenv('USE_JEMALLOC', '0'))
blade.set_variable('max_shards', 8)

# any BUILD / *.bld: read them
if blade.get_variable('use_jemalloc') == '1':
    deps.append('//thirdparty/jemalloc:jemalloc')
n = blade.get_variable('max_shards')
```

**Semantics**

- **`set_variable` is config-phase only.** BUILD files declare nothing; they only read. Calling it from a BUILD file aborts.
- **Reading an undeclared variable is an error** unless you pass a `default`. A typo'd or never-declared name fails loudly instead of silently yielding `None`. Pass `default` to make a variable optional: `blade.get_variable('opt', 'off')`.
- **Re-declaring a name is an error** unless `override=True`. An accidental double-set (e.g. across an included config file) is caught rather than silently taking the last value. Use `override=True` for intentional layering (a base config sets a default; a machine-specific include overrides it).
- **Values can be any type** (`str`, `int`, `list`, ...), not just strings.
- **The resolved variables are part of the configuration fingerprint.** Changing a value -- via `set_variable`, the env feeding it, or a `--define` override -- regenerates the affected per-target builds. This is what makes env-driven configuration incrementally correct.

**Command-line override: `--define`**

`blade build|test|run -D NAME=VALUE` (repeatable) overrides a declared variable from the command line -- handy for CI to pin a value or for a local experiment without editing `BLADE_ROOT`:

```bash
blade build --define use_jemalloc=1 //...
```

`--define` may only override a variable that `BLADE_ROOT` already declared with `set_variable` (overriding an undeclared name is an error), so the variable namespace stays defined solely by `BLADE_ROOT`. `--define` values are strings; if the declared variable is non-string, the override is taken verbatim as a string, so use `--define` for string/scalar variables.

### `blade.cc_toolchain` Object

> **Phase:** BUILD only

A read-only proxy to the current platform's C/C++ toolchain, for making platform-aware decisions in BUILD files.

**File naming properties** (all return `str`):

- `obj_suffix`: Object file suffix (e.g. `.o` on Linux/macOS, `.obj` on MSVC)
- `static_lib_suffix`: Static library suffix (e.g. `.a` on Linux/macOS, `.lib` on MSVC)
- `dynamic_lib_suffix`: Dynamic library suffix (e.g. `.so` on Linux, `.dylib` on macOS, `.dll` on MSVC)
- `lib_prefix`: Library name prefix (e.g. `lib` on Linux/macOS, `""` on Windows)
- `exe_suffix`: Executable file suffix (e.g. `""` on Linux/macOS, `.exe` on Windows)

**Platform properties** (all return `str`):

- `cc_vendor`: Compiler vendor: `'gcc'`, `'clang'`, or `'unknown'`
- `target_os`: Target OS being compiled for: `'darwin'`, `'linux'`, or `'windows'`. In cross-compilation this may differ from `blade.host_os`
- `target_arch`: Target CPU architecture: `'x86_64'`, `'aarch64'`, etc. In cross-compilation this may differ from `blade.host_arch`

**Tool lookup:**

- `tool(key)` → `str | None`: Return the path to a tool identified by *key*.
  Supported keys: `'cc'`, `'cxx'`, `'ld'`, `'ar'`, `'rc'`, `'as'`.
  Returns `None` when the tool is unavailable (e.g. `tool('rc')` is `None` on Linux).

**Examples:**

```python
cc = blade.cc_toolchain

# Compose output file names
obj = src + cc.obj_suffix
static_lib = cc.lib_prefix + 'foo' + cc.static_lib_suffix
binary = 'myapp' + cc.exe_suffix

# Query tool availability
if cc.tool('rc'):
    print('Resource compiler:', cc.tool('rc'))

# Cross-compilation-aware dependency selection
if cc.target_os == 'linux':
    libs.append('//thirdparty/linux_only:lib')
elif cc.target_os == 'darwin':
    libs.append('//thirdparty/mac_only:lib')

# Host platform (the machine running the build)
protoc = 'tools/protoc-%s-%s' % (blade.host_os, blade.host_arch)
```

---

## Function-valued Config Items

Config item values can be functions (including lambdas) that are evaluated lazily during the BUILD phase, allowing access to `blade` attributes that are only available at that stage (e.g. `cc_toolchain`).

### Basic Usage

```python
cc_test_config(
    # Dynamically determine config values based on build type and target architecture
    dynamic_link=lambda blade: not blade.build_type_is_debug() and blade.cc_toolchain.target_arch != 'ppc64le',
    heap_check=lambda blade: 'strict' if blade.cc_toolchain.target_arch != 'aarch64' else '',
)
```

### Limitations

- The function must accept **exactly 1 parameter** (the `blade` module). The arity is checked at assignment time.
- The return type must match the default value type of the config item. This is checked at evaluation time.
- **Functions cannot be mixed with plain values in the same list** — the entire item value is either a function or a plain value. Mixed lists such as `[func, 'value']` are not supported.
- The `append_` / `prepend_` prefixes cannot be used with function-valued items.
- Regular functions work, not just lambdas:

```python
def my_extra_incs(blade):
    return [
        'thirdparty/',
        'thirdparty/%s/' % blade.cc_toolchain.target_arch,
    ]

cc_config(
    extra_incs=my_extra_incs,
)
```

---

## `build_target` Deprecation

`build_target` is deprecated and will be removed in a future version. Use the following `blade.` replacements:

| `build_target` | Replacement | Notes |
| --- | --- | --- |
| `build_target.bits` | `blade.cc_toolchain` (inferred from target_arch) | Target bit width, e.g. 32 or 64. Requires function-valued config item at BUILD phase |
| `build_target.arch` | `blade.cc_toolchain.target_arch` | Target CPU architecture |
| `build_target.os` | `blade.cc_toolchain.target_os` | Target operating system |
| `build_target.is_debug()` | `blade.build_type_is_debug()` | Whether this is a debug build |

**Migration example:**

```python
# Old (in BLADE_ROOT)
def get_build_dir():
    return 'build%d_%s' % (
        build_target.bits,
        'debug' if build_target.is_debug() else 'release',
    )

# New
# Config-phase attributes can be used directly
# BUILD-phase-only attributes (e.g. cc_toolchain) require function-valued config items
cc_test_config(
    dynamic_link=lambda blade: not blade.build_type_is_debug() and blade.cc_toolchain.target_arch != 'ppc64le',
)
```
