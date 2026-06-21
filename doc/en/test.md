# Testing Support

Blade provides comprehensive support for test-driven development, enabling automated execution of multiple test programs through command-line interfaces.

## Incremental Testing

Blade test supports incremental testing by default to optimize test execution performance.

### Test Execution Conditions

Tests that have previously passed do not require re-execution in subsequent builds unless:

- **Dependency Changes:** Any modifications to test dependencies trigger regeneration
- **Test Data Changes:** Explicitly declared test data dependencies change (specified in BUILD files using `testdata` attribute)
- **Environment Variable Changes:** Related environment variables are modified
- **Argument Changes:** Test execution arguments are altered
- **Test Expiration:** Tests exceed their validity period

### Configuration Options

- **Environment Variables:** Configure test-related environment variables in `global_config.test_related_envs` (supports regex patterns)
- **Expiration Period:** Default test expiration time is 1 day
- **Failed Test Handling:** Failed tests run once more on retry; subsequent executions require rebuild or expiration
- **Behavior Override:** Use `global_config.run_unchanged_tests` or `--run-unchanged-tests` command-line option to modify default behavior

## Full Test Execution

To execute all tests unconditionally, use the `--full-test` option:

```bash
blade test common/... --full-test
```

### Always Run Attribute

`cc_test` targets support the `always_run` attribute, which forces execution during incremental testing regardless of previous results:

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    always_run = True
)
```

## Concurrent Testing

Blade supports parallel test execution to maximize testing efficiency.

### Configuration

Use `-t` or `--test-jobs N` to specify the number of concurrent test processes:

```bash
blade test //common... --test-jobs 8
```

### Exclusive Test Execution

An `exclusive` test runs **alone** — the test scheduler does not run any other
test at the same time. Use it in two situations:

1. **Interference / shared resource.** The test conflicts with others over a
   fixed resource — binding a well-known port, a fixed on-disk path, a system
   service, a singleton daemon — so running it alongside another instance is
   unreliable.
2. **Resource overload.** The test deliberately saturates the machine (CPU /
   memory / connection / fiber stress, overload or load tests). Run concurrently
   with the rest of the suite it can exhaust resources and fail or crash
   nondeterministically, even though it is correct in isolation.

```python
cc_test(
    name = 'zookeeper_test',     # interference: binds a fixed port
    srcs = 'zookeeper_test.cc',
    exclusive = True
)

cc_test(
    name = 'server_overload_test',   # overload: stresses the whole machine
    srcs = 'server_overload_test.cc',
    exclusive = True
)
```

Exclusive tests run serially, so prefer fixing genuine concurrency bugs over
marking tests exclusive; reserve it for the two cases above.

## Test Coverage Analysis

Blade supports code coverage analysis for C++, Java, and Scala tests using the `--coverage` option.

### C/C++ Coverage (gcov + gcovr)

C/C++ test coverage uses the compiler's [gcov](https://gcc.gnu.org/onlinedocs/gcc/Gcov.html) instrumentation (GCC, and Clang via `llvm-cov gcov`):

```bash
blade test //foo/... --coverage
```

- The coverage compile/link flags are added automatically; `.gcno`/`.gcda` data is produced during the test run.
- After the tests finish, Blade runs [gcovr](https://gcovr.com/) to produce a directory-navigable HTML report (drill down folder by folder to per-file line views) at `<build_dir>/cc_coverage_report/index.html` (plus `coverage.xml` in Cobertura format). Install it with `pip install gcovr`; if gcovr is absent, Blade just warns and skips the report.
- Sources under the build directory are excluded, so the report reflects your own code rather than generated sources (e.g. `*.pb.cc`) or vendored dependencies (vcpkg installs under the build dir).
- **Platform/toolchain:** `--coverage` works on gcc and clang on every platform, including **clang-cl** on Windows. Native MSVC `cl.exe` has no gcov-style instrumentation, so Blade skips the flag and warns once — on Windows compile with [clang-cl](config.md#using-clang-cl-on-windows) for LLVM source coverage, or use [OpenCppCoverage](https://github.com/OpenCppCoverage/OpenCppCoverage) (PDB-based, needs no rebuild).

### Go Coverage (go test -cover)

Go test coverage uses Go's built-in cover support:

```bash
blade test //foo/... --coverage
```

- `go_test` binaries are built with `-cover -covermode=count` and run with `-test.coverprofile`, dropping one profile per test.
- After the tests finish, Blade merges the profiles and runs `go tool cover -html` to produce a report at `<build_dir>/go_coverage_report/index.html`.

### Python Coverage (coverage.py)

Python test coverage uses [coverage.py](https://coverage.readthedocs.io/):

```bash
blade test //foo/... --coverage
```

- Each `py_test` runs under `coverage run -p`, writing a per-test data file.
- After the tests finish, Blade combines them and runs `coverage html` to produce a report at `<build_dir>/py_coverage_report/index.html`. Install it for the test interpreter with `pip install coverage`; if it is unavailable, Blade just warns and skips the report.
- Because the test runs from its packaged zip, file paths in the report carry a `.zip/` prefix.

**Separate build directory.** A `--coverage` build is instrumented differently from a normal build, so Blade gives it its own sibling build directory with a `_coverage` suffix — e.g. `build_release_coverage` instead of `build_release`. The plain build directory name is unchanged, so a normal build and a coverage build coexist without clobbering or rebuilding each other, and existing workspaces/scripts are unaffected.

### Java/Scala Coverage (JaCoCo)

Java/Scala test coverage requires JaCoCo configuration:

1. Download and extract [JaCoCo](https://www.jacoco.org/jacoco/) release build
2. Configure in BUILD file:

```python
java_test_config(
    ...
    jacoco_home = 'path/to/jacoco',
    ...
)
```

- Coverage reports are generated in `jacoco_coverage_report` directory under build directory
- Line coverage requires `global_config.debug_info_level` of `mid` or higher (requires `-g:line` compilation flag)

## Sanitizers

Sanitizers are compiler-based **runtime** bug detectors. Pioneered by Google in LLVM/Clang (AddressSanitizer, 2012) and later adopted by GCC, they instrument your code at compile time and check it as it runs for bugs that are otherwise silent or nondeterministic: out-of-bounds accesses and use-after-free (ASan), reads of uninitialized memory (MSan), undefined behavior (UBSan), data races (TSan), and memory leaks (LSan). Instead of a heisenbug you can only reproduce with luck, you get a symbolized report at the exact point of the fault. Coverage varies by toolchain — Clang supports the full set; GCC has all but MSan; MSVC provides only ASan.

Build and run an existing target tree under a sanitizer with a single command-line switch — no BUILD-file changes:

```bash
blade test //...                                # normal
blade test //... --sanitizer=address            # AddressSanitizer (alias: asan)
blade test //... --sanitizer=undefined          # UndefinedBehaviorSanitizer (alias: ubsan)
blade test //... --sanitizer=thread             # ThreadSanitizer (alias: tsan)
blade test //... --sanitizer=memory             # MemorySanitizer (alias: msan, Clang + Linux only)
blade test //... --sanitizer=address,undefined  # combined (ASan + UBSan)
```

A sanitizer is a **per-run choice** (a flag), not project config. `--sanitizer` applies to `build`, `run`, and `test`, and takes a comma-separated **set**: `address` (`asan`), `undefined` (`ubsan`), `leak` (`lsan`), `thread` (`tsan`), `memory` (`msan`) — on gcc / clang / Apple clang (MSan is Clang + Linux only; see below). The set is canonicalized (deduplicated and sorted) so `--sanitizer=ubsan,address` and `--sanitizer=address,undefined` are the same build. Sanitizers that use different runtimes can't be combined — `address`/`leak`/`undefined` compose, but `thread` and `memory` are each exclusive with `address`/`leak` and with each other (both still compose with `undefined`). A bad combination is a clear startup error.

- **Flags:** `-fsanitize=<set> -fno-omit-frame-pointer -g` are added to compiles and links (the link pulls in the sanitizer runtime). UBSan is made **fatal** (`-fno-sanitize-recover=undefined`) so a finding fails the test rather than just printing. For tests, Blade also sets sane `*_OPTIONS` defaults (e.g. `TSAN_OPTIONS=halt_on_error=1`) so a detection reliably exits non-zero — any value you set in the environment still wins. So `blade test` reports a detection as a failure.
- **MSVC:** the MSVC toolchain implements **only** AddressSanitizer — `--sanitizer=address` compiles with `/fsanitize=address` (plus `/Z7` for symbolized reports), links non-incrementally (`/INCREMENTAL:NO /DEBUG`; the ASan runtime is pulled in automatically), and puts the ASan runtime DLL on the test's `PATH`. Any other sanitizer on MSVC is a clear startup error.
- **MemorySanitizer:** `--sanitizer=memory` (alias `msan`) catches reads of uninitialized memory. It is **Clang + Linux only** — GCC has no MSan and the runtime is unavailable on macOS, so requesting it elsewhere is a clear startup error. Blade adds `-fsanitize-memory-track-origins=2` so a report points back to where the uninitialized value originated. MSan reports false positives unless **every** linked translation unit is instrumented: you must build (or supply) an MSan-instrumented C++ standard library and build your dependencies under MSan too — otherwise expect spurious reports from uninstrumented system libraries.
- **Isolated build directory:** a sanitized build is ABI/codegen-incompatible with a normal one, so it gets its own sibling dir with a sanitizer tag — `build_release_asan`. The plain `build_release` is untouched, so the two coexist without clobbering or rebuilding each other.
- **Per-target opt-out:** a target that must not be instrumented (intentional UB, a hot path, a wrapper around a non-instrumented prebuilt) sets `sanitize = False`. It still links (and still gets the runtime); only its own compiles drop the instrumentation. This works on MSVC too — since `cl` has no `-fno-sanitize`, Blade blanks the per-file `/fsanitize` flag for that target instead.

  ```python
  cc_library(name = 'crc32_hw', srcs = ['crc32_hw.cc'], sanitize = False)
  ```

- **Runtime options & suppressions:** set per-sanitizer run options from BLADE_ROOT, mapped onto the matching `*_OPTIONS` environment variable. Each value is a list, one option per element. These options are appended to Blade's defaults, and take effect only when that sanitizer is in `--sanitizer`. If you've already set that sanitizer's environment variable yourself (e.g. `ASAN_OPTIONS`), Blade uses it as-is and ignores the corresponding options from the config.

  To suppress a known-benign leak/race or a false positive, use the `suppressions=<file path>` option; the path is resolved relative to the workspace root and the file must exist. Suppression files use each sanitizer's **own** syntax: e.g. `leak:<name>` ([LeakSanitizer](https://github.com/google/sanitizers/wiki/AddressSanitizerLeakSanitizer#suppressions)), `race:<name>` / `called_from_lib:<lib>` ([ThreadSanitizer](https://github.com/google/sanitizers/wiki/ThreadSanitizerSuppressions)).

  ```python
  sanitizer_config(options = {
      'thread': ['suppressions=etc/tsan.supp', 'history_size=7'],
      'address': ['detect_stack_use_after_return=1'],
  })
  ```

## Test Exclusion

Blade supports selective test exclusion using the `--exclude-tests` parameter for batch test execution scenarios.

### Usage Example

```bash
blade test base/... --exclude-tests=base/string,base/encoding:hex_test
```

This command executes all tests in the base directory except those in `base/string` and the specific target `base/encoding:hex_test`.
