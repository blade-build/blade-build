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

### Go Coverage (go test -cover)

Go test coverage uses Go's built-in cover support:

```bash
blade test //foo/... --coverage
```

- `go_test` binaries are built with `-cover -covermode=count` and run with `-test.coverprofile`, dropping one profile per test.
- After the tests finish, Blade merges the profiles and runs `go tool cover -html` to produce a report at `<build_dir>/go_coverage_report/index.html`.

**Separate build directory.** A `--coverage` build is instrumented differently from a normal build, so Blade gives it its own sibling build directory with a `_coverage` suffix — e.g. `build64_release_coverage` instead of `build64_release`. The plain build directory name is unchanged, so a normal build and a coverage build coexist without clobbering or rebuilding each other, and existing workspaces/scripts are unaffected.

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

## Test Exclusion

Blade supports selective test exclusion using the `--exclude-tests` parameter for batch test execution scenarios.

### Usage Example

```bash
blade test base/... --exclude-tests=base/string,base/encoding:hex_test
```

This command executes all tests in the base directory except those in `base/string` and the specific target `base/encoding:hex_test`.
