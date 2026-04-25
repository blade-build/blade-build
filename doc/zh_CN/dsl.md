# DSL 和 API 模块

## DSL 语言

为了让构建更稳定，Blade 的 DSL 是受限制的 Python 语言，禁止了一些内置函数和关键字，包括但不限于：

- `exec`，`execfile`，`eval` 提高构建文件的一致性。
- `import` 请用 `blade` 的子模块。
- `print` 请用 `blade.console` 里的函数代替。

某些函数功能则有限制：

- `open` 只允许读模式访问

即使用 python 2 来运行 Blade，你也应当尽量采用反向移植的 python 3 的语法。

对于一些常用的额外功能，比如 `os.path.join` 之类的，需要使用 `blade` 模块中类似的子模块。如果有更多合理的扩充建议，欢迎给我们提 Issue。

要对现存的 `BUILD` 文件允许不受限制的 DSL 语言，设置 `global_config.unrestricted_dsl_dirs = [...]` 配置项，
要全局禁止 DSL 限制，设置 `global_config.restricted_dsl = False`。

## `blade` 模块

全局的 Blade API 模块，通过 `blade.` 来访问，包括：

- `current_source_dir()` 函数：当前 BUILD 文件所在的目录（相对于 workspace 的根目录）
- `current_target_dir()` 函数：当前 BUILD 文件所对应的构建输出目录（相对于 workspace 的根目录）
- `config` 子模块：读取 blade 的配置信息
- `console` 子模块：输出诊断信息
- `re` 子模块：正则表达式
- `path` 子模块：`os.path` 的一个受限制的子集

### `blade.config` 模块

访问配置信息，包括：

- `get_section()` 函数：获得一个配置节的内容，比如 `cc_config`，可以通过 `get` 方法读取其中的配置项
- `get_item()` 函数：获得一个具体的配置项，比如 `blade.config.get_item('cc_config', 'cppflags')`

### `blade.console` 模块

输出诊断信息，包括：

- `debug()` 函数：输出调试信息，默认不显示，用 `--verbose` 选项后才输出到屏幕
- `info()` 函数：输出提示信息
- `notice()` 函数：输出一些重要信息
- `warning()` 函数：输出警告信息
- `error()` 函数：输出错误信息，会导致构建失败

### `blade.path` 子模块

`os.path` 模块的一个子集，包括 `abspath()`、`basename()`、`dirname()`、`exists()`、`join()`、`normpath()`、`relpath()`、`sep`、`splitext()`。

### `blade.util` 模块

一些辅助函数，包括：

- `var_to_list()` 函数：如果是 `str`，将其转为单个元素的 `list`

### `blade.workspace` 模块

获得当前[工作空间](workspace.md)的一些信息，包括：

- `root_dir()` 函数：返回当前根工作空间的目录
- `build_dir()` 函数：返回工作空间下的 build 子目录名，比如 `build64_release`
