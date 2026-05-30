# Python 目标是如何构建与打包的

一个 `py_binary` 最终是 **shell 包装脚本 + 同名 `.zip`** 的对：zip 是应
用 bundle，wrapper 把它放到 `PYTHONPATH` 前面并 `python -m <entry>`。没
有 PEX、没有 PyInstaller —— 就是标准的 `zipapp` 风格加载。整条流水线刻
意保持小而可预期。

| 文件 | 作用 |
| --- | --- |
| `src/blade/py_targets.py` | `PythonLibrary`、`PythonBinary`、`PythonTest` |
| `src/blade/builtin_tools.py` | Python zip 组装器与 wrapper 脚本输出 |
| `src/blade/backend.py` | `pythonlibrary` / `pythonbinary` 规则 |
| `src/blade/test_scheduler.py` | `py_test` 启动（复用同一个 wrapper） |

## 1. Target

- **`py_library`** —— 输出一份 `.pylib` 元数据文件：一个 Python 字面
  量，含该库源文件及其 MD5、以及包基目录。没有可执行产物；它纯粹是
  `py_binary` 之后要采集的信息单元。
- **`py_binary`** —— `PythonLibrary` 之上再一步打包：产出 `<name>.zip`
  （bundle）与 `<name>`（shell wrapper）。
- **`py_test`** —— `PythonBinary` 带 `run_in_shell=True`。测试框架
  （unittest、pytest…）由用户 `main` 模块自行调用，blade 不强加 runner。

## 2. 源与依赖采集

`base='//path'` 控制源路径 → import 名的映射。`base='//proto'` 时，源
`proto/foo/bar.py` 在 import 时就是 `foo.bar`。`_get_entry()` 把
`main` 属性拆 `.py`、改分隔符，得到点分名。

源可以是原始 `.py`、`.egg`、或 `.whl`。`.pylib` 把每项记为
`(path, md5)`；binary 之后走 `expanded_deps`，把每个 dep 的 `.pylib`
里的文件列表收齐。**刻意**没有原生扩展通路：deps 产出的 `.so`/`.dylib`
（如某个 `cc_library` 被 Python target 引用）不会被这套机制拉入。

## 3. `py_binary` 打包

`builtin_tools.py` 里的 `python_binary` builtin 完成真正的组装：

1. 读每份输入 `.pylib`，按配置的 base 计算每个源在 zip 里的 arcname。
2. 用 target 的 `exclusions`（fnmatch 模式）过滤 —— 用于把测试 fixture
   或平台相关文件排除在 bundle 外。
3. `.egg`/`.whl` 输入在内存中解压并再压回，丢掉元数据目录
   （`.dist-info/`、`EGG-INFO/`）与预编译的 `.pyc`；字节码改在运行时
   按需生成，回避跨 Python 小版本的不兼容。
4. 追踪哪些目录至少有一个源；为命名空间路径上但本身没 `__init__.py` 的
   目录注入空 `__init__.py`（命名空间包不必用户手工补 stub）。
5. 经 `write_if_changed` 写 zip：内容未变则保留 mtime —— ninja 的
   `restat` 能据此剪掉依赖该 bundle 的下游 rule。

wrapper 平台不同但都很小：

- POSIX（`#!/bin/sh`）：`PYTHONPATH="$DIR/$NAME.zip:$PYTHONPATH" exec
  "$BLADE_PYTHON_INTERPRETER" -m <entry>`。
- Windows（`.bat`）：对应的 `set PYTHONPATH=...;%PYTHONPATH%` 再
  `python -m <entry>`。

`BLADE_PYTHON_INTERPRETER` 让运行 shell / CI 不重打包就能选具体解释器版
本；wrapper 默认走宿主 `python3`/`python`。所以一份 `py_binary` 构建产
物可在多个 Python 版本上启动（只要用户代码兼容）。

## 4. 测试执行

`py_test` 设 `run_in_shell=True`。测试调度器（见
[测试执行](test_execution.md)）看到该标记后用 shell 启动 wrapper 脚本
—— 后者再分发到 `python -m <entry>`。blade 不出测试框架：用户 `main` 模
块自己调 `pytest.main()` / `unittest.main()` / 自定义 runner。pass/fail
由退出码决定，runfiles / testdata 走所有 test rule 共享的那一套。

## 5. 技术细节与用户体验优化

- **bundle 不放 `.pyc`。** 字节码在首次 import 时进用户运行时缓存；
  bundle 跨 Python 小版本保持可移植。代价是每个进程一次的字节码生成；
  收益是不必为每个解释器重打 bundle。
- **`write_if_changed` 写 zip。** 组装内容未变（典型场景：碰了 BUILD
  但没改内容）会保留 zip mtime，依赖它的 rule 看到"输入没变"。多数上
  游测试数据文件的重建对下游零代价。
- **`.pylib` 里的源 MD5。** ninja depfile 抓的是文件系统级变更，但
  `.pylib` 中显式的 MD5 让库的身份基于内容而非 mtime —— 能识别
  `touch`-only 改动从而不触发不必要的工作。
- **只有 `base` 这一个旋钮要学。** 多数其它构建系统要求一张"源 ↔ 包"
  映射；这里 `base` + 正常目录布局就够了。entry 计算就是纯路径 → 点分
  名重写，运行时只是多一个 `PYTHONPATH` 入口。
- **新机器即可启动。** `(wrapper, wrapper.zip)` 这对自包含，只要
  `$PATH` 上有 Python 解释器即可，无需安装步骤。
- **blade 不做的事。** 不打包原生扩展、不为声明的 requirements 跑
  `pip install`、不重写 shebang —— 这些刻意留给项目惯例处理（把 wheel
  vendor 进一个 `py_library`，或依赖运行时环境）。
