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
- `--profile-generate[=path]` / `--profile-use[=path]` - [Profile-Guided Optimization](#profile-guided-optimization-pgo) (gcc, clang, and native MSVC). Phase 1 instruments, phase 2 rebuilds with the collected profile.

## Profile-Guided Optimization (PGO)

Profile-Guided Optimization (PGO), also known as Feedback-Directed Optimization (FDO), is a technique that uses profile data collected from a program's real execution to guide the compiler's optimizations.

PGO is a **global build mode** (not a per-target attribute): you instrument the whole build, run a representative workload, then rebuild using the collected profile. It is wired for **gcc, clang, and native MSVC**; both phases use a dedicated `build_*_pgo` directory so they never clobber your normal `build_*` objects.

```bash
# Phase 1 — instrument, then run a representative workload to collect data
blade build //foo:server --profile-generate=/tmp/pgo
./build_release_pgo/foo/server   # exercise the hot paths

# Phase 2 — rebuild optimized, using the profile
blade build //foo:server --profile-use=/tmp/pgo
```

Toolchain differences blade handles for you:

- **gcc** reads the `.gcda` files directly and adds `-fprofile-correction` (tolerates the count skew of multithreaded programs). Both phases **must** share the build dir — gcc keys its `.gcda` lookup by object path — which the dedicated `build_*_pgo` dir guarantees.
- **clang** needs a *merged* `.profdata`: its instrumented run emits `.profraw`, and `-fprofile-use=` must point at a merged file, not a directory. Point `--profile-use` at the directory of `.profraw` (or an already-merged `.profdata`) and **blade runs `llvm-profdata merge` for you**. clang's `-fprofile-correction` does not exist, so it is not emitted.
- **MSVC** uses whole-program (LTCG) instrumentation: blade compiles with `/GL`, links the instrument phase with `/LTCG /GENPROFILE` and the optimize phase with `/LTCG /USEPROFILE` (and archives with `lib /LTCG`). The instrumented run writes `<binary>!N.pgc` next to the `<binary>.pgd`, and `/USEPROFILE` **auto-merges** them on the optimize link — no `pgomgr` step. The `.pgd` is keyed to the output name, so the shared `build_*_pgo` dir is what lets the optimize phase find the instrument phase's profile. The `path` argument is gcc/clang-specific and is not needed on MSVC (the profile lives next to the binary).

Blade owns the build flags and the clang merge step; producing a *representative* workload (and deciding when a profile is stale) is your job. Profiles are **not** portable across compilers — instrument, run, and optimize all on one toolchain.

> The **instrument** build defines `BLADE_PGO_GENERATE` (a Blade-private macro, not a compiler/industry standard), so source can flush the profile runtime in long-running or forking servers — e.g. `#ifdef BLADE_PGO_GENERATE` → `__llvm_profile_write_file()` (clang) / `__gcov_dump()` (gcc) / `PgoAutoSweep(...)` (MSVC). The **use** build and **AutoFDO** define nothing: those binaries should behave exactly like a normal release.

### Sample-based PGO (AutoFDO)

The instrumentation-based PGO above needs two builds — instrument, then optimize — which is cumbersome, and the instrumented run carries real overhead.

AutoFDO is the **no-instrumentation** flavor of PGO: instead of an instrumented build, you sample a *normal optimized* binary and rebuild with the result. The collection runs at ~1% overhead (vs ~2× for instrumentation), so the profile can come from real production traffic. Works on **gcc/clang** (sample with `perf`) and **native MSVC** (sample with `xperf` — see SPGO below). Uses a dedicated `build_*_autofdo` dir.

```bash
# Phase 1 — build with AutoFDO-friendly debug info, then sample under perf
blade build //foo:server --autofdo-generate
perf record -b -- ./build_release_autofdo/foo/server     # -b = LBR branch records

# Convert perf.data -> a sample profile yourself (it needs the collected binary):
#   clang: llvm-profgen --perfdata=perf.data --binary=build_release_autofdo/foo/server --output=foo.prof
#   gcc:   create_gcov  --binary=build_release_autofdo/foo/server --profile=perf.data --gcov=foo.afdo

# Phase 2 — rebuild using the converted profile
blade build //foo:server --autofdo-use=foo.prof
```

**Typical usage — one build per release (steady state).** Unlike instrumentation PGO (which always needs a separate *slow instrumented* build), AutoFDO's collection binary is a *normal* binary, so once you have a profile you combine both phases into **a single build that is both optimized and collectable**:

```bash
# Each release: optimize with last cycle's profile AND stay sample-able for the next.
blade build //foo:server --autofdo-generate --autofdo-use=foo.prof
# ship it -> sample it in production -> convert -> feeds the *next* release's --autofdo-use
```

`--autofdo-generate` + `--autofdo-use` compose on all three toolchains (gcc/clang add the debug info alongside `-fprofile-sample-use`/`-fauto-profile`; MSVC links `/spgo` alongside `/spdin:` — verified legal on MSVC 14.51, x64 + ARM64). So in steady state every build is simultaneously "optimize with last profile" and "collect for next" — no dedicated extra build. (The very first time, run `--autofdo-generate` alone to bootstrap a profile.) The AutoFDO debug flags are cheap, so you can also bake them into your release config and pass just `--autofdo-use` daily.

- **clang** → `-fprofile-sample-use=<profile>`; the collection build adds `-fdebug-info-for-profiling` + `-funique-internal-linkage-names` (better sample-to-source mapping).
- **gcc** → `-fauto-profile=<profile>`; the collection build needs only the `-g` Blade already emits (the clang debug flags are clang-only).
- **`--autofdo-use` takes an *already-converted* profile**, not a raw `perf.data` — the converter (`llvm-profgen`/`create_gcov`) needs the collected binary, which Blade doesn't have at build time. A raw `perf.data` is detected and rejected with the conversion command.
- **native MSVC** uses its own sample-PGO — **SPGO** ([Sample Profile Guided Optimization](https://devblogs.microsoft.com/cppblog/introducing-sample-profile-guided-optimization-in-msvc/), VS 2022 / 2026 with MSVC 14.51+), which Blade drives from the same `--autofdo-*` flags: `--autofdo-generate` links `/spgo` (collect build), `--autofdo-use=app.spd` links `/LTCG /spdin:app.spd` (both compile `/GL`). You sample with **`xperf`** (IP sampling on any CPU, LBR on Intel Haswell+/AMD Zen 4+/ARM64 ARMv9.2-A+) and convert with **`SPDConvert`** into the `.spd` — those are your step, as with perf. **clang-cl** can't do sample-PGO on Windows (SPGO is cl-only; AutoFDO needs `perf`), so `--autofdo-*` is skipped there with a warning.

**Platform availability (collection vs use).** Sample-PGO *collection* needs hardware sampling: gcc/clang need `perf` + **LBR** (a **bare-metal / PMU-passthrough x86_64 Linux** host — ARM Linux VMs typically expose no PMU/LBR, so `perf record -b` fails there); native MSVC needs `xperf` (IP sampling works on any CPU, including ARM64). **macOS has no sample-PGO collection path at all** (no `perf`, no SPGO; Instruments/`sample`/`dtrace` don't feed `llvm-profgen`) — the `--autofdo-use` flag is still portable, so a Linux-collected profile *can* be applied there, but cross-OS/arch reuse is imperfect and unsupported. Where you can't collect, **use instrumentation PGO** (`--profile-generate`/`--profile-use`) — fully functional everywhere with no special hardware.

> **References:** [GCC AutoFDO tutorial](https://gcc.gnu.org/wiki/AutoFDO/Tutorial) · [MSVC SPGO](https://devblogs.microsoft.com/cppblog/introducing-sample-profile-guided-optimization-in-msvc/)

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
