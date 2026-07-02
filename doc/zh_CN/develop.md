# 开发

## 代码结构

```text
src/
├── blade/              # 主源码包
│   ├── main.py         # CLI 入口
│   ├── command_line.py # 命令行参数解析
│   ├── config.py       # 配置加载（blade.conf, BLADE_ROOT 等）
│   ├── workspace.py    # 工作空间发现与管理
│   ├── load_build_files.py  # BUILD 文件加载与 DSL 沙箱
│   ├── dependency_analyzer.py # 拓扑排序与依赖解析
│   ├── backend.py      # 后端构建系统生成（Ninja）
│   ├── build_manager.py     # 构建编排
│   ├── ninja_runner.py      # Ninja 调用
│   ├── binary_runner.py     # 执行构建产物
│   ├── test_runner.py       # 测试沙箱与执行
│   ├── test_scheduler.py    # 并行测试调度
│   ├── toolchain.py    # 编译工具链抽象（GCC、MSVC、Clang）
│   ├── *_targets.py    # 构建规则实现（cc、java、py、go 等）
│   ├── target.py       # 目标基类
│   ├── build_rules.py  # 规则注册基础设施
│   ├── dsl_api.py      # 暴露给 BUILD 文件的 safe `blade.*` DSL 模块
│   ├── blade_types.py  # 共享类型别名（StrOrList、StrOrListOpt）
│   ├── util.py         # 通用工具函数
│   ├── console.py      # 日志与诊断输出
│   ├── config.py       # 配置模式定义
│   └── inclusion_check.py  # C/C++ 头文件依赖检查
├── tests/
│   └── unit/           # 单元测试（pytest，无需工具链）
└── test/               # 集成/端到端测试（runall.sh / blade_main_test.py，需要工具链）
```

**规则模块**（`*_targets.py`）各自定义一个或多个构建规则：

| 模块 | 规则 |
| --- | --- |
| `cc_targets.py` | `cc_library`、`cc_binary`、`cc_test`、`cc_plugin`、`prebuilt_cc_library`、`foreign_cc_library` |
| `java_targets.py` | `java_library`、`java_binary`、`java_test` |
| `py_targets.py` | `py_library`、`py_binary`、`py_test` |
| `proto_library_target.py` | `proto_library` |
| `go_targets.py` | `go_library`、`go_binary`、`go_test` |
| `scala_targets.py` | `scala_library`、`scala_test` |
| `cu_targets.py` | `cu_library`、`cu_binary`、`cu_test` |
| `gen_rule_target.py` | `gen_rule` |
| `lex_yacc_target.py` | `lex_yacc_library` |
| `resource_library_target.py` | `resource_library` |
| `windows_resources_target.py` | `windows_resources` |
| `package_target.py` | `package` |
| `sh_test_target.py` | `sh_test` |

## 基本原理

### 加载配置

Blade 启动后，依次尝试通过 `execfile` 函数执行多个路径下的配置文件。这些配置文件都是 Python 源文件，调用 blade 里预先定义好的配置函数，把配置项更新到 `blade.config` 的配置 dict 里。

然后，命令行选项里与 `global_config` 同名的选项会覆盖更新到配置中，使得命令行参数的优先级最高。

### 加载 BUILD 文件

Blade 从命令行指定的构建目标展开，通过受限的 `execfile` 沙箱逐个执行 `BUILD` 文件。BUILD 文件代码被执行时，调用规则函数（如 `cc_library(...)`）把目标注册到 blade 内部的数据结构里。

所有传递依赖对应的 BUILD 文件都会被递归加载，直到所有依赖都被加载。

### 依赖分析

Blade 从命令行指定的目标根出发，进行拓扑排序，得出有序的构建目标列表。

### 生成后端构建文件

各目标逐一生成后端构建动作（Ninja 规则），写入后端构建文件（如 `build.ninja`）。

### 执行后端构建系统

Blade 调用后端构建工具（Ninja）执行实际构建。生成的构建文件（如 `build.ninja`）会保留在 build 目录里，供增量构建和调试使用；只有 `blade clean` 才会清理它。

### 运行测试

测试目标先被构建，然后在沙箱环境中并行执行。所有测试完毕后汇总结果并输出报告。

## 实现专题

各子系统实现原理的深入文档，大致按 `blade build` 的执行顺序排列：

- [配置项的加载、分层与读取](develop/configuration.md)
- [BUILD 文件的发现、加载与注册](develop/build_file_loading.md)
- [内置函数与 `blade.*` DSL](develop/dsl_api.md)
- [Visibility 的实现与执行](develop/visibility.md)
- [依赖分析与 ninja 文件生成](develop/dependency_analysis.md)
- [`gen_rule`：自定义构建步骤与其它 target 如何感知它](develop/gen_rule.md)
- [自定义规则（`define_rule`）实现原理](develop/custom_rule.md)
- [C/C++ 程序的构建](develop/cc_build.md)
- [C/C++ 头文件依赖检查（hdrs check）实现原理](develop/hdrs_check.md)
- [静态未定义符号检查（`check_undefined`）实现原理](develop/check_undefined.md)
- [`export_map`（符号导出控制）实现原理](develop/export_map.md)
- [vcpkg 支持实现原理](develop/vcpkg.md)
- [`proto_library` 的多语言代码生成](develop/protobuf_build.md)
- [Java 与 Scala 程序的构建](develop/java_scala_build.md)
- [Python 目标的构建与打包](develop/python_build.md)
- [console：构建进度面板与 ninja 状态流水线](develop/console.md)
- [`blade test` 如何运行用户测试](develop/test_execution.md)
- [blade-build 自身是如何被测试的](develop/self_testing.md)

## 测试

### 单元测试（`src/tests/unit/`）

快速的离线测试，验证独立模块。不依赖工具链或系统环境。

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src python -m pytest src/tests/unit/ -v
```

### 集成测试（`src/test/`）

端到端测试，对 `src/test/testdata/` 下的夹具数据驱动真实的构建/测试流程。需要可用的 C/C++ 工具链（GCC、MSVC 或 Clang）。

```bash
src/test/runall.sh          # 运行全部集成测试
src/test/run.sh <test_name> # 运行单个测试（如 cc_library_test）
```

### 类型检查

```bash
pip install -r requirements-dev.txt
pyright
```

## 新增构建规则

1. **创建目标类** — 在新增或已有的 `*_targets.py` 模块中创建目标类，继承 `Target`（或合适的子类）并实现 `generate()` 方法。
2. **定义规则入口函数**（如 `windows_resources()`）—— 此函数负责将 BUILD 友好的类型（`StrOrListOpt`）通过 `var_to_list` / `var_to_list_or_none` 规范化为 `list[str]`，创建目标实例，通过 `build_manager.instance.register_target()` 注册。
3. **暴露到 DSL** — 将规则函数加入 `blade/__init__.py` 和 [dsl_api.py](../../src/blade/dsl_api.py)。
4. **添加集成测试数据** — 在 `src/test/testdata/<rule_name>/` 下放置 BUILD 文件和源文件夹具，在 `src/test/<rule_name>_test.py` 添加测试类，并把该测试类注册到 `src/test/blade_main_test.py` 的 `TEST_CASES` 列表（CI 只运行列在其中的用例；`src/tests/unit/integration_suite_coverage_test.py` 会校验没有遗漏）。
5. **更新文档** — 在 [build_rules/cc.md](build_rules/cc.md)（或新规则类别对应的新文件）中添加说明。

### 核心设计模式

- **`StrOrList` / `StrOrListOpt`** — 规则入口函数接受 `str | list[str]` 联合类型，以方便 BUILD 文件书写。始终在传入父类构造函数之前，通过 `var_to_list()`（可选参数用 `var_to_list_or_none()`）规范化为 `list[str]`。
- **工具链抽象**（`toolchain.py`）— 平台相关的构建细节（编译器、链接器、文件后缀）封装在 `ToolChain` 基类之后。规则实现通过查询工具链对象而非分支判断 `os.name`。
- **`blade.cc_toolchain`** — 通过 DSL 暴露给 BUILD 文件的只读代理对象，用于跨平台判断（文件命名、能力查询等）。

## 调试与诊断

大多数子命令支持 `--stop-after` 选项，可选参数为 `{load, analyze, generate, build}`，控制在指定阶段完成后停止：

```bash
blade build --stop-after generate
```

此命令在生成后端构建系统描述文件（如 `build.ninja`）后停止，可用于检查生成结果。

`--profiling` 选项在 blade 结束后输出性能分析报告。可与 `--stop-after` 组合用于分析不同阶段的性能。

### 向后端构建器（ninja）传递选项

`--backend-builder-options` 可把任意选项直接转发给 ninja（见 [`ninja_runner.py`](../../src/blade/ninja_runner.py)）。调试时最常用的：

```bash
# 为什么某个目标会被（重新）构建——尤其是每次都重建的？让 ninja 解释它的判断。
blade build //foo/... --backend-builder-options="-d explain"

# 打印 ninja 实际执行的命令（-v），或只做 dry-run 不实际构建（-n）。
blade build //foo/... --backend-builder-options="-v"
```

`-d explain` 会为每条将要执行的 edge 打印它被判定为“脏”的*原因*——输入更新、输出比输入旧、命令行变化、或记录的依赖（`deps`/depfile）已不存在。当构建不增量（尤其是每次都重建）时，这是首先要用的工具。

也可以直接对生成的构建文件运行 ninja（在 `blade build --stop-after generate` 之后尤其方便——此时只生成了构建文件、尚未运行 ninja）。blade 从工作区根目录运行 ninja，所以用相对 build 目录的路径；加 `-n` 做只解释不构建的 dry-run：

```bash
ninja -f build_release/build.ninja -d explain -n
```

提示：ninja 只会作为 `deps = msvc` 的副作用从控制台输出中剥掉它的 `msvc_deps_prefix`（`Note: including file:`）行；其余工具输出都原样回显。在 MSVC 上，blade 的 `cc_wrapper.py` / `link_wrapper.py`（生成在 build 目录里）会过滤 ninja 不处理的编译器/链接器噪音。

## CI

GitHub Actions 工作流在每次 PR 和 push 到 `master` 时运行：

| 工作流 | 用途 |
| --- | --- |
| **Python package** | Ubuntu 上的单元测试 + 集成测试 + E2E smoke + pyright（Python 3.10–3.14） |
| **macOS CI** | macOS 上的平台相关单元测试子集 + in-process smoke + E2E smoke |
| **Windows CI** | Windows 上的平台相关单元测试子集 + in-process smoke + E2E smoke |
| **CodeQL** | 安全分析 |
| **Check Markdown links** | 文档链接有效性检查 |

## 打包

代码根目录下的 `dist_blade` 可将源码打包为 zip 用于部署，与 `blade` 启动脚本和 `blade.conf` 放在同一目录即可。

## 其他资料

以下两篇社区对 Blade 实现原理的分析，基于 Blade 早期版本，有些过时，仍有参考价值：

- [浅谈 blade 中 C++Build 的设计与实现](https://tsgsz.github.io/2013/11/01/2013-11-01-thinking-in-design-of-blade-cpp-build/)
- [锋利的 blade 到底锋利在哪里](http://blog.sina.com.cn/s/blog_4af176450101bg69.html)
