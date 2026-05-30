# BUILD 文件是如何被发现、加载与注册的

Blade 不会预先扫描整个工作区。它从你点名的 target 出发，**按需**发现所需
的 BUILD 文件，在受限命名空间中 `exec()` 之，再沿 `deps` 把更多 BUILD
拉进来，直到可达集合闭合。这让加载耗时与工作区中真正涉及的那一部分大体
成正比。

| 文件 | 作用 |
| --- | --- |
| `src/blade/target_pattern.py` | 把 CLI 中的 spec 规范化为 `path:name` 键 |
| `src/blade/load_build_files.py` | 发现、`exec`、沙箱、按 deps 做 BFS |
| `src/blade/build_rules.py` | BUILD 文件中可调用的名字集合 |
| `src/blade/build_manager.py` | 单例：target 数据库、键冲突检测 |
| `src/blade/target.py` | `Target` 基类、源位置捕获 |

## 1. 从命令行 pattern 到 BUILD 文件集合

用户可以写 `//foo/bar:lib`、`foo/bar`、或 `//foo/bar/...`。
`target_pattern.normalize()` 把这些规范化为 `<path>:<name>`：仅目录写法
变成 `<dir>:*`（该 BUILD 里所有 target），`<dir>/...` 变成
`<dir>/...:...`（递归标记）。

随后 `_expand_target_patterns()` 把 pattern 转成一组起始 BUILD 文件：

- `path:name`：把它记作 direct target，只加载该包的 BUILD。
- `path:*`：把 `path` 加进 `starting_dirs`。
- `path/...`：用 `os.walk()` 走目录树，收集每个含 `BUILD` 的目录，并尊重
  两个边界标记：
  - `.bladeskip`：整棵子树跳过。
  - 嵌套的 `BLADE_ROOT`：永远不跨入另一个工作区。

这个递归遍历是**唯一**直接枚举文件系统的地方；其它 BUILD 都靠 `deps`
关系扩展出来。

## 2. 加载：`exec()` 在受限 globals 中

每个 BUILD 文件是一段 Python 脚本，由 `exec_file(path, globals_dict,
None)` 执行。globals 是 `_get_globals_for_build_file()` 为每个文件**新建**
的：

- 注册过的全部规则名（`cc_library`、`proto_library`、`gen_rule`、…），来自
  `build_rules.get_all()`。
- `blade` 模块（`dsl_api.get_blade_module()`）—— 见
  [内置函数与 `blade.*` DSL](dsl_api.md)。
- 当 `global_config.restricted_dsl` 打开（默认开）时，把
  `__builtins__` 替换为 `restricted.safe_builtins`，去掉 `__import__`、
  `exec`、`eval`，把 `open()` 收窄为只读，等等。

**BUILD 文件本身不通过参数告诉自己"我在哪儿"**。进程级别的
`build_manager.instance` 暴露 `get_current_source_path()`，在每次
`exec_file()` 前后被设置/恢复。BUILD 中的规则函数读取它来构成 target
键（`<path>:<name>`）。诊断用的源位置在同一时刻捕获，于是 BUILD 内任何
错误都精准定位到用户代码的那个文件和行号，而不是 blade 内部的栈帧 ——
这是一个刻意的用户体验优化。

## 3. Target 注册与键空间

`cc_library(name='x', ...)` 执行时构造一个 `Target`，在 `__init__` 里调
`build_manager.instance.register_target(self)`。该单例持有唯一的
`__target_database` dict，按 `<path>:<name>` 索引。重复的键在**加载期**
就 fatal，提示信息里带两处定义的源位置 —— 比延后到构建期诊断更便宜，也
不会被忽略。

系统库 dep（如 `#dl`）会规范化成伪键 `#:dl`，与真正 path 完全隔离开
（任何 path 包含 `#` 都是非法的）。

## 4. 按 deps 迭代加载（lazy loading）

起始 BUILD 加载完后，`_load_related_build_files()` 在 deps 图上做 BFS：

- 从队列里弹出一个 target 键，加载它的 BUILD（如尚未加载），把它的
  `deps` 中未访问过的入队。
- `processed_dirs` dict 短路任何已加载过的目录（无论成功失败），保证一次
  `blade` 调用中每个 BUILD 至多 `exec` 一次。
- 落在 `.bladeskip` 或其它嵌套 `BLADE_ROOT` 范围内的 target 会被丢弃并
  报错 —— 即使别的 BUILD 引到它们也无法触达。

环检测在后面 `dependency_analyzer._expand_target_deps()` 里完成：递归中
维护一个 path 集合，再访问到正在展开中的 target 就报
`Loop dependency` fatal，并指出造成环的那条边。

## 5. glob 与 `load()`

- `glob(include, exclude, allow_empty=False)` 以 BUILD 自身目录为基准，用
  `pathlib.Path.glob()` 匹配，支持 `**`。exclude 第二趟过滤：精确字符串走
  集合成员判定（更快），通配符走 `path.match()`。`allow_empty=True` 是
  "我清楚可能匹配为空" 的显式开关，避免无意写出空匹配。
- `load('//path:ext.bld', sym1, sym2)` 暴露扩展文件里的具名符号。结果按
  扩展文件绝对路径缓存在 `__loaded_extension_info`，多个 BUILD 引用同一
  扩展时只 `exec` 一次。

## 6. 用户体验优化要点

- **基于 deps 闭包的惰性加载**让加载耗时与工作区中真正涉及的切片大体成
  正比。在大型 monorepo 里，这是 `blade build //foo:bar` 不必读整棵
  workspace 的主因。
- **BUILD 去重（`processed_dirs`）**把潜在的指数级 BFS 退化成线性：每个
  BUILD 在一次 `blade` 调用中只加载一次，不管多少边指向它。
- **扩展缓存（`__loaded_extension_info`）**是同样思路在另一层：被许多
  BUILD `load()` 的扩展文件也只 `exec` 一次。
- **每 target fingerprint**（以 `#Fingerprint=...` 写在 per-target
  `.build.ninja` 第一行）让增量构建在 target 的加载期输入（srcs、deps、
  config digest、blade revision）未变时直接跳过 ninja 文件重写。详见
  [依赖分析与 ninja 生成](dependency_analysis.md)。
- **错误锚定到 BUILD 源位置。** 每个 `Target` 在构造时记录其所在 BUILD
  的文件路径与行号；后续诊断（缺 dep、未知属性、重名、…）都以
  `BUILD:lineno: error:` 形式输出，大多数编辑器能直接跳转。这是 blade
  在开发者体验上最显眼的投入之一。
- **`.bladeskip` 与嵌套 `BLADE_ROOT`** 让工作区把某些目录（vendor 源、临
  时目录…）从递归遍历中隔离开，不必改 BUILD 用显式 deps 来达成同样效
  果。它们对初始 `...` 展开和 BFS 都生效。
