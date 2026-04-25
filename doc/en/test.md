# Testing Support

Blade provides complete support for test-driven development, and can run multiple test programs automatically through command line.

## Incremental Testing

Blade test supports incremental testing defaultly to speed up the execution of tests.

Tests that have already been PASSED do not need to run again in the next build and test unless:

* Any dependency changes to tests cause it to regenerate.
* Tests dependent test data changes, this dependency is explicitly dependent, the user needs to specify using a BUILD file, such as testdata.
* Tests where the related environment variable has changed.
* Test arguments change.
* Test expired.

Test related environment variable names can be configureed in the `global_config.test_related_envs` config item, regex is allowed.

Text expired time is 1 day.

For any failed test, if it is the first time, it will run at the next time. but after the retry, it will not run again until it is rebuilt or expired.
You can use `global_config.run_unchanged_tests` config item or `run-unchanged-tests` command line option to change the behavior.

## Full Test

If you need to run the full test, use the --full-test option, such as blade test common/... --full-test, all tests will be run unconditionly.
In addition, cc_test supports the `always_run` attribute, which is used to always run every time during incremental testing, regardless of the last execution result.

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    always_run = True
)
```

## Concurrent Testing

Blade test supports concurrent testing. The concurrent test runs the test that need to be run after build.
You can use `-t` (or `--test-jobs N`) to set the number of concurrent tests. Blade will execute max N test processes concurrently.

Example:

```bash
blade test //common... --test-jobs 8
```

## Non-concurrent Testing

For some tests that may not run in concurrent because they may interfere with each other, you can add the `exclusive` attribute.

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    exclusive = True
)
```

## Test Coverage

When building and running tests, with the `--coverage` option, blade will include coverage-related compile options, and collect coverage data after the tests finished, currently only support C++, Java and Scala.

C/C++ test coverage is implemented by gcc's [gcov](https://gcc.gnu.org/onlinedocs/gcc/Gcov.html). After the test is run, you need to execute a third-party tool such as gcov or lcov to generate a test coverage report.

To generate java/scala test coverage, you need to download and unzip a [jacoco](https://www.jacoco.org/jacoco/) releases build, and configure it correctly:

```python
java_test_config(
    ...
    jacoco_home = 'path/to/jacoco',
    ...
)
```

The java/scala test coverage report will be generated into the `jacoco_coverage_report` dir under the build dir.

If `global_config.debug_info_level` is `low` or lower, line coverage will not be generated. because `-g:line` is required.

## Exclude Specified Tests

Blade supports explicitly excluding specified tests with the `--exclude-tests` parameter, which is useful when you need to run a large number of tests in batches and expect to exclude some ones. E.g:

```bash
blade test base/... --exclude-tests=base/string,base/encoding:hex_test
```

Indicates to run all tests in the base directory, but exclude all tests in `base/string` and `base/encoding:hex_test`.
