# 测试支持

Blade 对测试驱动开发提供了完善的支持，可以通过命令自动运行测试程序。

## 增量测试

Blade test 支持增量测试，可以加快测试的执行。

已经通过的测试，在下一次构建和测试时不需要再跑，除非：

* 测试的任何依赖变化导致其重新生成。
* 测试依赖的测试数据改变，这种依赖为显式依赖，需要用户在 BUILD 文件中指定，比如 testdata。
* 测试所依赖的环境变量发生改变。
* 测试参数（test arguments）改变。
* 测试结果过期。

测试相关的环境变量名可以通过 `global_config.test_related_envs` 配置项设置，支持正则表达式。

测试过期时间是一天。

对于失败的测试，如果这是第一次失败，下次还会尝试重新运行。但是如果还是失败，就不会再运行，除非发生了重新构建或者过期。
你可以用 `global_config.run_unrepaired_tests` 配置项或者 `--run-unrepaired-tests` 命令行参数改变这个行为。

## 全量测试

如果需要进行全量测试，使用 `--full-test` 选项，比如 `blade test common/... --full-test`，这时所有测试都需要运行。
另外，cc_test 支持了 `always_run` 属性，用于在增量测试时，不管上次的执行结果，每次总是重新运行。
```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    always_run = True
)
```

## 并行测试

Blade test 支持并行测试，在构建完成后并发执行本次需要运行的测试用例。

```bash
blade test [targets] --test-jobs N
```

`-t, --test-jobs N` 设置并行测试的数目，Blade 会让 N 个测试进程并行执行。

## 非并行测试

对于某些因为可能相互干扰而不能并行跑的测试，可以加上 exclusive 属性

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    exclusive = True
)
```

## 测试覆盖率

构建和运行测试时，加上--coverage 参数，blade 就会加入覆盖率相关的编译选项，并在运行时收集测试覆盖率数据，目前仅支持 C++、Java 和 Scala。

C/C++测试覆盖率，是通过 gcc 的[gcov](https://gcc.gnu.org/onlinedocs/gcc/Gcov.html)实现的。测试运行完后，需要自己执行 gcov 或者 lcov 之类的第三方工具生成测试覆盖报告。

要生成 Java/Scala 测试覆盖率报告，你需要下载并解压[jacoco](https://www.jacoco.org/)，然后进行配置：

```python
java_test_config(
    ...
    jacoco_home = 'path/to/jacoco',
    ...
)
```

测试报告会生成到 build 目录下的 `jacoco_coverage_report` 目录里。

如果调试符号级别（global\_config.debug\_info\_level）太低，低于或等于`low`，那么生成的覆盖率报告里会缺少行覆盖率。
Jacoco 需要 `-g:line` 编译选项才能生成行覆盖率。

## 排除指定的测试

Blade 支持通过--exclude-tests 参数显式地排除指定的测试，当需要批量运行大量的测试，而又期望排除某些测试时，这个选项就很有用。例如：

```bash
blade test base/... --exclude-tests=base/string,base/encoding:hex_test
```

表示运行 base 目录下所有的测试，但是排除 base/string 里所有的测试以及 base/encoding:hex_test。
