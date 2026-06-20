# blade-build 自身是如何被测试的

blade-build 的测试金字塔有三层——单元（UT）、集成 / E2E、烟雾
（smoke），各自的范围、运行器、CI 形态都不同。覆盖率在集成层的子进程
运行中捕获，跨层与跨 Python 版本合并后上报。

| 层 | 位置 | 驱动 | 覆盖范围 |
| --- | --- | --- | --- |
| **UT** | `src/tests/unit/` | `unittest`/`pytest`，无子进程 | 单模块纯 Python 逻辑的隔离测试 |
| **集成 / E2E** | `src/test/`（`blade_test.py` harness） | 启动真实 `blade` 对着 `testdata/` | 在小工作区上端到端跑整条流水线 |
| **Smoke** | `.github/workflows/*` + 同级 `blade-test` 仓库 | 两种形态（见下） | 健全性检查 + 跨仓接受性 |

外加并行运行的类型检查（`pyright`）与文档链接检查。

## 1. 单元测试

`src/tests/unit/` 下是普通 Python 测试模块——通常 `unittest.TestCase`
子类，有时由 `pytest` 跑。**严格 hermetic**：无子进程、无 testdata 工
作区、无编译器。UT 直接 import 待测 blade 模块，构造极简的内存状态，
对结果断言。示例（仅示形态、文档不追具体 case）：工具链抽象的平台命名
逻辑、`var_to_list` 边界辅助、隔离运行的头文件 `Checker`。

本地：`python3 -m unittest discover -s src/tests/unit -p '*_test.py'`
（`src/tests/unit/runall.sh` 帮你把 `PYTHONPATH` 设好）。CI 跑
`pytest src/tests/unit`。Linux 上 Python 版本矩阵覆盖支持区间（当前
3.10–3.14）；macOS/Windows 挑能在本机平台上跑得动的平台无关单元子集。

## 2. 集成 / E2E 测试

harness 是 `src/test/blade_test.py`，基类是 `TargetTest`。一个测试：

- 调 `doSetUp('subdir', target='...')` 切到共享 `src/test/testdata/`
  工作区，并重置其 `build_release/` 产物。
- 调 `runBlade('build')`（或 `'test'`），它启一个真实
  `../../../blade build <targets> --generate-dynamic --verbose`，把
  stdout/stderr 捕获到文件。
- 用 `inBuildOutput(kwlist)` / `findBuildOutput(kwlist)` 断言捕获输
  出。

`testdata/` 是**单一共享工作区**，按域（cc、java、lex_yacc、
hdr_dep_check、guard_suppression、header_only_incstk…）分子目录。每个
集成测试只清自己 target 的产物，因此**串行**运行——在当前规模下，为并
行而复制 testdata 还不必要。

本地 runner 是 `src/test/run.sh <file>`（整套用 `runall.sh`）。CI 上集
成测试是 `python-package.yml` 里耗时较长的作业之一。blade 子进程跑的
是树内代码（以 `../../../blade` 调用），同一次运行就能验证
`src/blade/...` 的改动。

## 3. Smoke

两个东西都叫 "smoke"：

- **进程内 smoke**（`macos-ci.yml` / `windows-ci.yml`）：import blade
  模块、调 `create_toolchain()`、检查 per-platform 命名输出符合期望
  （`libfoo.a` vs `foo.lib`、macOS 上 clang、Windows 上 msvc）。无子
  进程、无真实构建——只是快速检查"这个包至少能在本 OS 上正确 import"。
- **跨仓 E2E smoke**（`python-package.yml` / `macos-ci.yml` /
  `windows-ci.yml`）：checkout 同级 `blade-test` 仓库，对其 fixtures
  跑 `./blade.sh test //suites/...`（cc_basic、java_basic、
  lex_yacc_basic、py_basic、resource_basic、…）。这是能抓出"只在真实
  工具链下才显形"的集成回归的层级——而且门控在 UT + 集成之后，仅当便
  宜层都过了才跑。

## 4. 覆盖率

捕获发生在集成层，由 `src/test/run.sh`：

```sh
BLADE_PYTHON_INTERPRETER="$PYTHON -m coverage run \
    --source=$ROOT/src/blade --rcfile=$ROOT/.coveragerc"
```

所以集成测试启的每个 blade 子进程都在 `coverage` 下运行。`.coveragerc`
里 `parallel = true`，会按 PID 写 `.coverage.<pid>` 文件——必要，因为
blade 构建期还自己启子进程（编译器、codegen 工具…），单一 `.coverage`
文件会有写竞争。

测试结束后 `run.sh` 调 `coverage combine` 合并 per-process 文件，再
`coverage report` 输出终端摘要。

CI 上，单一 Python 版本（通常是集成矩阵里挑选的那个）再走一步：集成完
后，单元测试在 `coverage run -m pytest src/tests/unit` 下重跑，再用
`coverage combine --append` 把它合到集成基线上。合并后的文件通过
`coveralls --service=github` 上传到 Coveralls。该上传步骤标
`continue-on-error`——Coveralls 服务波动不让 build 失败。

## 5. CI 编排

`.github/workflows/`：

- `python-package.yml`（Ubuntu）——UT + 集成 + e2e-smoke + 覆盖率合并
  + Coveralls 上传。Python 版本矩阵；覆盖率合并只在其中一版上做，避免
  重复上传。
- `macos-ci.yml`——平台相关 UT 子集 + 进程内 smoke + e2e smoke。Python
  矩阵子集。
- `windows-ci.yml`——Windows 上的对应作业。
- 辅助：`pyright`（类型检查）、`codeql`（静态分析）、`check-md-links`
  （文档链接检查）。它们与测试金字塔独立。

跨 OS 作业刻意跑 blade **平台形状**部分（工具链检测、命名、MSVC 专属
路径），而不是把整套 Linux 套件再跑一遍。代价是：那些 smoke 矩阵没覆
盖到的 macOS/Windows 上的逻辑回归，只有下游用户报告才会暴露——改工具
链代码时尤需留意。

## 6. 技术细节与用户体验优化

- **集成串行跑同一份 testdata 工作区。** 这是最大的约束，也是套件保
  持小巧的主因。取舍：清理逻辑简单 + harness 简单，对换 per-test 复制
  testdata 的并行。当前规模下前者明显更优。
- **`BLADE_PYTHON_INTERPRETER`** 是覆盖率借用的接缝，但它也允许开发
  者无需改脚本即可调试某个具体 Python 版本。把它设成
  `python3.13 -m coverage run ...` 就能用与 CI 相同的 flag 单独跑某失
  败测试并采集覆盖率。
- **`.coveragerc` 里的 `parallel = true` 是必须的。** 否则一个 blade
  子进程再启 Python 子进程（包含检查、builtin 工具…）就会在
  `.coverage` 上并发写出损坏文件。
- **跨层合并覆盖率。** 集成完后把单元用 `coverage run` + `coverage
  combine --append` 接上去，上传的数字才反映两层；不然单元独立覆盖
  辅助函数（集成也覆盖了）就会重计或分报。
- **Coveralls 上传 `continue-on-error`。** 把外部上报视作 best-effort
  让构建状态诚实：CI 不会因第三方 API 故障变红。
- **跨 OS smoke 刻意便宜。** 在 macOS/Windows 跑完整集成会慢而脆（工
  具链版本不同、库路径不同）；进程内 smoke + 对 `blade-test` 的 E2E
  以低代价获得高信号。
- **Hermetic UT vs 重集成。** 这道分割让内圈循环快：UT 上的改-跑循环
  亚秒；集成留给"wiring 是否变了"的场景。
