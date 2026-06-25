# Command Line Reference

## Basic Command Line Syntax

```bash
blade <subcommand> [options]... [target patterns]...
```

## Subcommands

Blade supports the following subcommands:

- `build` - Build specified targets
- `test` - Build and execute tests
- `clean` - Clean up specified targets
- `dump` - Export useful information
- `query` - Query target dependencies
- `run` - Build and execute a single executable target
- `init` - Create a `BLADE_ROOT` in the current directory
- `root` - Print the workspace root directory

### `blade init`

Bootstrap a new workspace by creating a `BLADE_ROOT` file in the current directory. The file contains commented-out configuration blocks that you uncomment and edit as needed.

```bash
blade init                       # default: C/C++ config block
blade init --lang=cc,java        # include C/C++ and Java config blocks
blade init --lang=all            # include every supported language
blade init --force               # initialize even inside an existing workspace
```

`--lang` accepts a comma-separated list of `cc` (a.k.a. `c++`), `java`, `scala`, `go`, `python`, `proto`, or `all`.

By default `blade init` refuses to run when the current directory is **at or under an existing `BLADE_ROOT`**, because that would create a nested workspace (a `BLADE_ROOT` already in this directory, or one in any parent directory). Pass `--force` to initialize anyway — this overwrites a `BLADE_ROOT` in the current directory, or creates a nested one beneath a parent workspace.

## Target Pattern Syntax

Target patterns are space-separated lists that identify build targets. These patterns are supported in command lines, configuration items, and target attributes.

### Supported Pattern Formats

- `path:name` - Specific target within a path
- `path:*` - All targets within a path
- `path` - Equivalent to `path:*`
- `path/...` - All targets within a path and all subdirectories recursively
- `:name` - Target in the current directory

### Path Resolution Rules

- **Full Paths:** Paths starting with `//` represent absolute paths from the workspace root
- **Direct Targets:** Patterns without wildcards in the name component are considered direct targets
- **Default Behavior:** When no target is specified, Blade builds all targets in the current directory (excluding subdirectories)
- **Empty Expansion:** Specifying `...` as the end target will not fail if the path exists, even if expansion results in no targets

### Directory Search Behavior

- **Recursive Search:** Blade recursively searches `BUILD` files for `...` target patterns
- **Exclusion Mechanism:** Place an empty `.bladeskip` file in directories to exclude them from recursive searches
- **Shell Compatibility:** With [ohmyzsh](https://ohmyz.sh/) installed, bare `...` expands to `..\..` - use `./...` instead

## Target Tag Filtering

Blade supports filtering build targets using tag expressions via the `--tags-filter` option. Each target supports [tags attribute](build_file.md#tags).

### Filter Expression Syntax

- **Tag Names:** Full tag names like `lang:cc`, `type:test`
- **Logical Operators:** `not`, `and`, `or`
- **Group Selection:** `group:name1,name2` syntax for selecting multiple tags within the same group (equivalent to `(group:name1 or group:name2)`)
- **Complex Expressions:** Use quotation marks for expressions containing spaces

### Filtering Examples

- `--tags-filter='lang:cc'` - Filter `cc_*` targets
- `--tags-filter='lang:cc,java'` - Filter `cc_*` and `java_*` targets
- `--tags-filter='lang:cc and type:test'` - Filter `cc_test` targets
- `--tags-filter='lang:cc and not type:test'` - Filter `cc_*` targets excluding `cc_test`

### Filtering Scope

Tag filtering applies only to targets expanded through wildcard patterns on the command line. Direct targets and their dependencies are not filtered. Any target dependent on an unfiltered target remains in the build regardless of its tag matching status.

### Tag Discovery

To discover available tags for filtering:

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

## Subcommand Options

Different subcommands support different options. Run `blade <subcommand> --help` for complete option lists.

### Common Command Line Options

- `-m32`, `-m64` - Target architecture (32-bit/64-bit), defaults to automatic detection
- `-p PROFILE` - Build profile (`debug`/`release`), defaults to `release`
- `-k`, `--keep-going` - Continue execution after non-fatal errors
- `-j N`, `--jobs=N` - Parallel build jobs (Blade defaults to automatic parallelization)
- `-t N`, `--test-jobs=N` - Parallel test execution for multi-CPU systems
- `--test-timeout-multiplier=FACTOR` - Scale every per-test wall timeout by `FACTOR` for the current run (default `1.0`). Use on slower-than-baseline machines (e.g. shared CI runners) where the `global_config.test_timeout` configured for normal hardware is too tight. Affects only the current run; not stored in config. Example: `blade test --test-timeout-multiplier=3 ...`
- `--verbose` - Display complete command output for each executed command
- `-h`, `--help` - Display help information
- `--color=yes/no/auto` - Enable/disable colored output
- `--exclude-targets` - Comma-separated target patterns to exclude from loading
- `--generate-dynamic` - Force generation of dynamic libraries (`.so` / `.dylib` / `.dll`) for every `cc_library`, even those not depended on by a `dynamic_link` executable. Useful when you want to validate shared-link closure across the project or smoke-test that every library can be loaded dynamically. Overridden per-target by `cc_library(..., generate_dynamic = False)` (the library still stays static).
- `--cc-check-undefined` - Force-enable the [`cc_library` static undefined-symbol check](build_rules/cc.md#static-undefined-symbol-check) for this invocation, overriding [`cc_library_config.check_undefined`](config.md#cc_library_config). Per-target `check_undefined = False` still wins.
- `--no-cc-check-undefined` - Force-disable the static undefined-symbol check for this invocation.
- `--generate-java` - Generate Java files for proto_library and swig_library
- `--generate-php` - Generate PHP files for proto_library and swig_library
- `--generate-go` - Generate Go files for proto_library
- `--gprof` - Enable GNU gprof profiling support. **Linux only** (gcc and clang): `-pg`/gprof instrumentation only works on Linux. On macOS the flag is silently ignored (Darwin clang accepts `-pg` but treats it as a no-op, and there is no gprof tool / `gmon.out`); on Windows MSVC does not understand it. Blade skips the flag and warns once on these platforms — use `--coverage`, or a native sampling profiler (Instruments/`sample` on macOS, `perf` on Linux).
- `--coverage` - Generate code coverage reports (supports GNU gcov and Java jacoco). For C/C++ on **gcc and clang** (every platform, including **clang-cl** on Windows) this is the `--coverage` gcov instrumentation, reported with gcovr. On Windows with **native MSVC `cl.exe`** (which has no gcov-style instrumentation) blade instead collects coverage at run time with `Microsoft.CodeCoverage.Console.exe` (it instruments the test exe dynamically via its PDB — no compile flag — and emits Cobertura), then merges the per-test reports into `cc_coverage_report/coverage.cobertura.xml`. The tool ships with Visual Studio / the Build Tools; ARM64 targets are not supported by it.
- `--profile-generate[=path]` / `--profile-use[=path]` - Instrumentation [Profile-Guided Optimization](optimization.md#profile-guided-optimization-pgo) (gcc/clang/MSVC): phase 1 instruments, phase 2 rebuilds with the collected profile.
- `--autofdo-generate` / `--autofdo-use=<profile>` - Sample-based PGO / [AutoFDO](optimization.md#sample-based-pgo-autofdo) (gcc/clang + native MSVC SPGO): sample a normal optimized binary and rebuild — no instrumentation.
- `--lto[=thin|full|no]` - [Link-Time Optimization](optimization.md#link-time-optimization-lto) (gcc / clang / native MSVC / clang-cl), overriding the [`cc_config.lto`](config.md#cc_config) policy: bare `--lto` = ThinLTO, `--lto=full` = monolithic, `--lto=no` = off. Honored even in debug (escape hatch).

## Usage Examples

```bash
# Build all targets in current directory (excluding subdirectories)
blade build

# Build all targets in current directory and all subdirectories
blade build ...

# Build specific target named 'urllib' in current directory
blade build :urllib

# Build all targets under 'app' directory, excluding 'sub' subdirectory
blade build app... --exclude-targets=app/sub...

# Build and test all targets from workspace root and common subdirectory
blade test //common/...
blade test base/...

# Build and test specific target in base subdirectory
blade test base:string_test
```

## Command Line Completion

Blade provides basic command line completion after installation. For enhanced completion functionality, install [argcomplete](https://pypi.org/project/argcomplete/).

### Installation

```console
pip install argcomplete
```

For non-root installations, add the `--user` parameter:

```console
pip install --user argcomplete
```

### Configuration

Add the following line to `~/.bashrc`:

```bash
eval "$(register-python-argcomplete blade)"
```
