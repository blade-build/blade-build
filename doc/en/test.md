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

For tests that cannot run concurrently due to potential interference, use the `exclusive` attribute:

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    exclusive = True
)
```

## Test Coverage Analysis

Blade supports code coverage analysis for C++, Java, and Scala tests using the `--coverage` option.

### C/C++ Coverage (GCOV)

C/C++ test coverage utilizes GCC's [gcov](https://gcc.gnu.org/onlinedocs/gcc/Gcov.html) implementation:

- Coverage-related compilation flags are automatically included
- Coverage data is collected after test execution
- Generate reports using third-party tools like gcov or lcov

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
