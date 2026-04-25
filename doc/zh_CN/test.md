# 测试支持

Blade 为测试驱动开发（TDD）提供了完善的支持，支持通过命令行自动执行多个测试程序。

## 增量测试

Blade 的 `test` 子命令默认启用增量测试，以优化测试执行性能。

### 触发重新执行的条件

之前已通过的测试在后续构建中无需再次执行，除非满足以下任一条件：

- **依赖变更：** 测试所依赖的任何目标发生了变化，需要重新生成
- **测试数据变更：** 在 BUILD 文件中通过 `testdata` 属性显式声明的测试数据发生变化
- **环境变量变更：** 相关的环境变量被修改
- **参数变更：** 测试执行参数发生变化
- **测试过期：** 超出了有效期

### 配置选项

- **环境变量：** 通过 `global_config.test_related_envs` 配置与测试相关的环境变量（支持正则表达式）
- **过期时间：** 测试默认有效期为 1 天
- **失败处理：** 失败的测试在下一次会被再执行一次；再次失败后需等构建变化或有效期过期后才会重新运行
- **行为覆盖：** 通过 `global_config.run_unchanged_tests` 或命令行选项 `--run-unchanged-tests` 可覆盖默认行为

## 全量测试

如需无条件执行所有测试，使用 `--full-test` 选项：

```bash
blade test common/... --full-test
```

### always_run 属性

`cc_test` 目标支持 `always_run` 属性，无论增量测试如何判断，都强制执行：

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    always_run = True
)
```

## 并行测试

Blade 支持并行执行测试，以最大化测试效率。

### 配置方式

使用 `-t` 或 `--test-jobs N` 指定并发的测试进程数：

```bash
blade test //common... --test-jobs 8
```

### 互斥执行的测试

对于某些由于相互干扰而无法并行运行的测试，可以通过 `exclusive` 属性声明独占执行：

```python
cc_test(
    name = 'zookeeper_test',
    srcs = 'zookeeper_test.cc',
    exclusive = True
)
```

## 测试覆盖率分析

Blade 支持 C++、Java、Scala 测试的覆盖率分析，使用 `--coverage` 选项即可开启。

### C/C++ 覆盖率（GCOV）

C/C++ 测试覆盖率基于 GCC 的 [gcov](https://gcc.gnu.org/onlinedocs/gcc/Gcov.html) 实现：

- 自动加入覆盖率相关的编译选项
- 测试执行后自动收集覆盖率数据
- 可通过 `gcov`、`lcov` 等第三方工具生成报告

### Java / Scala 覆盖率（JaCoCo）

Java / Scala 测试覆盖率需要配置 JaCoCo：

1. 下载并解压 [JaCoCo](https://www.jacoco.org/jacoco/) 发布包
2. 在 BUILD 文件中配置：

```python
java_test_config(
    ...
    jacoco_home = 'path/to/jacoco',
    ...
)
```

- 覆盖率报告会生成到构建目录下的 `jacoco_coverage_report` 目录
- 若需要行级覆盖率，`global_config.debug_info_level` 需设置为 `mid` 或更高（要求编译时带 `-g:line` 选项）

## 测试排除

Blade 支持通过 `--exclude-tests` 参数在批量执行测试时选择性地排除部分测试。

### 使用示例

```bash
blade test base/... --exclude-tests=base/string,base/encoding:hex_test
```

该命令会执行 `base` 目录下的所有测试，但排除 `base/string` 目录下的所有测试，以及具体的 `base/encoding:hex_test` 目标。
