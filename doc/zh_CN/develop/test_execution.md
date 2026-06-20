# `blade test` 如何运行用户测试

测试执行建立在常规构建之上：可执行体就绪后，blade 决定本次哪些值得
跑，给每个测试装配 sandbox，并行调度（独占测试单走一遍），抓取结果，更
新历史，下次就能跳过未变的。

| 文件 | 作用 |
| --- | --- |
| `src/blade/test_runner.py` | 发现、基于历史的去重、结果汇总 |
| `src/blade/test_scheduler.py` | 并行调度、工作线程、超时 |
| `src/blade/binary_runner.py` | per-test runfiles 目录、env、testdata 装配 |
| `src/blade/config.py` | `cc_test_config`、`global_config.test_timeout`、`test_related_envs` |

## 1. 流水线概览

1. `TestRunner.run()` 收集每个 `*_test` target（`cc_test`、`java_test`、
   `py_test`、`scala_test`、`sh_test`、…），对每个调 `_run_reason()`
   询问本次是否需要跑。
2. 对需要跑的，`BinaryRunner._prepare_env()` 构建 per-test
   `<target>.runfiles` 目录，符号链接共享库、复制 testdata、拼装
   env 字典。
3. `TestScheduler.schedule_jobs()` 把任务分发到工作线程。
   `exclusive=True` 的测试在并行批之后由单工作线程串行执行一遍。
4. 全部完成后，runner 把结果合入测试历史文件，写 JSON 汇总，并打印
   passed/failed/unchanged/repaired 计数。

## 2. Per-test 环境

每个测试以 `cwd=<target>.runfiles` 启动。该目录每次重建；里面放：

- **构建目录的符号链接**（`runfiles/<build_dir_basename> ->
  <绝对构建目录>`）。blade 自编的共享库以相对构建路径为身份（没有
  soname / 没有 `@rpath`），所以靠这条符号链接才能让
  `build_release/lib/libfoo.so` 在测试 cwd 下解析得到。这是 issue
  #1167 的修复，也让 macOS dyld 与 Linux ld.so 行为一致而无需按 OS
  分支。
- **按 soname 的符号链接**给确实带 soname 的预制库
  （`libcrypto.so.1.0.0` 等）。运行时通过 blade 设置的
  `LD_LIBRARY_PATH`（指向 runfiles）找到它们。
- **装配好的 testdata**：从 target 的 `testdata` 属性复制（也从
  `<target>.testdata` 旁路文件读取）。条目可以是普通路径或
  `(src, dst)` 元组；以 `//` 起头的路径是工作区相对的。

传给测试的 env 是 `os.environ` 副本加上：

- `LD_LIBRARY_PATH`（runfiles + 配置的 `run_lib_paths`）。
- 若 `java_config.java_home` 配置了，把 `java_home/bin` 加到 `PATH`。
- 视情况加 `GTEST_COLOR`、`GTEST_OUTPUT=xml`、`HEAPCHECK`（per-target）、
  `PPROF_PATH`、`BLADE_COVERAGE`。

Windows 跳过 soname 符号链接那一路（PE 加载也不看那里），所以这套
sandbox 是 POSIX 形态的。

## 3. 并行调度

`TestScheduler` 走两遍：

- **普通遍**：最多 `global_config.test_jobs` 个工作线程从共享队列取任
  务。每个 worker 跑一个 `subprocess.Popen`、抓 stdout/stderr、应用
  per-test 超时、把结果回报主线程。
- **独占遍**：`exclusive=True` 的测试串行到另一队列，在普通遍完成后
  由单工作线程跑。适合争夺固定资源（端口、共享文件、系统级配置）的测
  试。

主线程上的超时观察者在任务超过限额时发 `SIGTERM`（再 `SIGKILL`）；退
出码经 `_signal_map()` 翻译，结果行写作 `SIGTERM:-15` 而不是裸负数。

runner 在两种输出模式间切换。单工作线程 + 正常详细程度时，把测试
stdout 直接流过去，交互式 `blade test` 一个 target 就像直接跑测试。多
工作线程（或安静模式）时把每个测试的输出缓冲，测试结束后一整块输出，
避免并行时行间穿插。

## 4. 结果、汇总与测试历史

每个任务记一份 `TestRunResult(exit_code, start_time, cost_time)`。
runner 合并：

- 通过：更新历史，把之前失败的标 "repaired"。
- 失败：`fail_count++`，新失败时记 `first_fail_time`，加进
  `new_failed_tests`。

历史文件 `<build_dir>/.blade.test.stamp` 按测试存最后一次 `TestJob`
（binary MD5、testdata MD5、env MD5、args）与 `TestHistoryItem`（运行
结果、失败计数）。它是一段 Python `repr()`，加载用 `eval()`，因此 schema
保持可读、对字段扩展前向兼容。

每次还写一份结构化 `blade-bin/.blade-test-summary.json`，把同样数据按
`passed` / `failed` / `unchanged` / `repaired` / `new_failed` /
`unrepaired` / `excluded` 分桶。外部工具（CI 看板、IDE 集成）从这里读，
而不是抓终端文本。

## 5. 未变测试的增量去重

§4 与 §5 的整套机制——测试历史、`.blade-test-summary.json`、`unchanged`
与 `unrepaired` 分桶——主要面向**大仓的 CI 体验**：在几千个测试的仓库
里，一个长期失败的测试不该卡住整条 CI，但也不能从汇总里消失。这套机制
是一条旁路：让这类测试**继续**出现在 `unrepaired` 列表（带首次失败时间
和重试次数），推动负责人去修，同时不绑架其它测试。

`_run_reason()` 决定一个测试本次是否需要跑：

- `EXPLICIT`——命令行点名了。
- `FULL_TEST`——`--full-test` 完全绕过去重。
- `ALWAYS_RUN`——target 设了 `always_run=True`。
- `BINARY` / `TESTDATA` / `ENVIRONMENT` / `ARGUMENT`——对应 MD5 自上次
  通过以来变了。环境用 `global_config.test_related_envs`（正则列表）
  决定哪些 env 重要，避免 `EDITOR` 改名让全套测试失效。
- `STALE`——上次跑距今超过截止时间（目前一天）。
- `NO_HISTORY`——首跑。
- `FAILED` / `RETRY`——上次失败，且未被 unrepaired-skip 策略覆盖。

以上都不触发就静默跳过，汇总里计入"unchanged"。长期失败的测试可放入
"unrepaired"桶（汇总里给出 first-fail 时间与重试次数），不必每次构建都
跑——一个倔强的失败测试不该卡住整个本该绿色的套件。

## 6. 技术细节与用户体验优化

- **Runfiles + 按 cwd 解析的 dylib。** 那条 `runfiles/<build_dir>` 符
  号链接让 blade 自编的 `.so`/`.dylib` 在测试 cwd 下可被找到，无需特
  殊 install name 或 rpath。代价是每个测试一次 syscall；收益是测试在
  Linux 与 macOS 上行为相同。
- **独占测试单独一遍。** 把独占测试混进并行队列要么限并行度，要么做
  per-test 门控。再走一遍单工作线程更简单，也让并行路径的逻辑保持简
  洁。
- **env MD5 用可配置允许列表。** `test_related_envs` 让工作区声明哪些
  env 真正影响结果，化妆性改动（终端程序、shell PS1）不会让缓存失效。
  真正依赖比如 `TZ` 的测试把它加进列表即可。
- **输出捕获 vs 流式。** 按工作线程数与详细程度自动选择，常见的单
  target 调试场景体验良好（不缓冲），同时保留几千测试并行时清晰的输
  出格式。
- **JSON 汇总并行于终端输出。** 汇总文件让 CI 接结构化结果而不是抓测
  试 log；带有时间、退出码、失败计数，以及 "new failed" / "repaired"
  这种人会在意的增量。
- **`unrepaired` 策略。** 默认跳过已知坏掉的测试（带清晰汇总行）是刻
  意的 UX 选择：坏测试不该拖住其余，但汇总仍写"still unrepaired,
  failing since X, retried N times"，免得被忘掉。
- **覆盖率清理。** `--coverage` 打开时，最后 `_clean_for_coverage()`
  会移除每个测试 runfiles 下的 build 目录符号链接，避免覆盖率工具走
  runfiles 时跟进真实构建目录。
