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

全局的 Blade API 模块，通过 `blade.` 来访问。

### 配置阶段可用属性

以下属性在配置文件 `BLADE_ROOT` 和 BUILD 文件中均可使用：

- `host_os` 属性：构建主机（运行构建的机器）的操作系统名称：`'darwin'`、`'linux'` 或 `'windows'`
- `host_arch` 属性：构建主机的规范化 CPU 架构：`'x86_64'`、`'aarch64'` 等
- `build_type` 属性：当前构建类型：`'debug'` 或 `'release'`
- `build_type_is_debug()` 函数：返回 `True` 表示当前为 debug 构建
- `console` 子模块：输出诊断信息
- `path` 子模块：`os.path` 的一个受限制的子集
- `re` 子模块：正则表达式
- `util` 子模块：辅助函数

注意：构建环境（host）不一定等同于编译目标环境（target）。`host_os` 和 `host_arch` 主要用于调用构建主机上的开发工具等场景。对于编译目标相关的平台判断，应使用 `blade.cc_toolchain` 的 `target_os` 和 `target_arch` 属性。

### 仅 BUILD 阶段可用的属性

以下属性仅在 BUILD 文件加载阶段可用，在 `BLADE_ROOT` 配置阶段访问会报错。如需在配置项中使用这些属性，请使用[函数式配置项](#函数式配置项)延迟到 BUILD 阶段求值：

- `cc_toolchain` 对象：当前平台 C/C++ 工具链的只读代理
- `config` 子模块：读取配置信息
- `workspace` 子模块：工作空间信息
- `current_source_dir` 属性：当前 BUILD 文件所在的目录（相对于 workspace 根目录）
- `current_target_dir` 属性：当前 BUILD 文件对应的构建输出目录（相对于 workspace 根目录）

### 仅配置阶段可用的属性

以下属性仅在 `BLADE_ROOT` 配置阶段可调用，在 BUILD 文件中调用会报错：

- `getenv(name, default=None)` 函数：读取环境变量。详见下文 [`blade.getenv`](#bladegetenv)。

---

### `blade.config` 子模块

> **可用阶段：** 仅 BUILD 阶段

访问配置信息，包括：

- `get_section()` 函数：获得一个配置节的内容，比如 `cc_config`，可以通过 `get` 方法读取其中的配置项
- `get_item()` 函数：获得一个具体的配置项，比如 `blade.config.get_item('cc_config', 'cppflags')`

### `blade.console` 子模块

输出诊断信息，包括：

- `debug()` 函数：输出调试信息，默认不显示，用 `--verbose` 选项后才输出到屏幕
- `info()` 函数：输出提示信息
- `notice()` 函数：输出一些重要信息
- `warning()` 函数：输出警告信息
- `error()` 函数：输出错误信息，会导致构建失败

### `blade.path` 子模块

`os.path` 模块的一个子集，包括 `abspath()`、`basename()`、`dirname()`、`exists()`、`join()`、`normpath()`、`relpath()`、`sep`、`splitext()`。

### `blade.util` 子模块

一些辅助函数，包括：

- `var_to_list()` 函数：如果是 `str`，将其转为单个元素的 `list`
- `var_to_list_or_none()` 函数：与 `var_to_list()` 类似，但 `None` 值原样透传

### `blade.workspace` 子模块

> **可用阶段：** 仅 BUILD 阶段

获得当前[工作空间](workspace.md)的一些信息，包括：

- `root_dir` 属性：返回当前根工作空间的目录
- `build_dir` 属性：返回工作空间下的 build 子目录名，比如 `build64_release`

### `blade.getenv`

> **可用阶段：** 仅 `BLADE_ROOT` 配置阶段。在 BUILD 文件中调用会报错并终止构建。

在配置阶段读取一个环境变量。这是 blade 中**唯一**允许显式读环境变量的入口——blade 在其它任何位置都不会隐式读取 `CC`、`CXX` 等环境变量。

```python
def getenv(name: str, default: str | None = None) -> str | None
```

**典型用法**：通过 CI matrix 选择 toolchain，不需要把 matrix 的形状写进 BLADE_ROOT。

```python
# BLADE_ROOT
cc_toolchain_config(
    name = 'default',
    kind = 'gcc',
    cc = blade.getenv('CC', 'gcc'),
    cxx = blade.getenv('CXX', 'g++'),
)
```

之后 CI 工作流的 `CC=gcc-10 CXX=g++-10 ./blade build ...` 即可选中对应版本。任何接受字符串的配置字段都可以这样写。

**为什么只在配置阶段？** 把 env 访问收敛到全局配置层，所有 env 依赖都集中在一个可审计的文件（BLADE_ROOT）里，BUILD 文件保持 hermetic——相同源码在相同 target 下产物不随 env 变化。如果 BUILD 阶段需要 env 衍生的值（比如 `foreign_cc_library` 要把 CC/CXX 传给 Makefile），从已解析的 toolchain 或 config 读：

```python
# BUILD 或 *.bld 文件
cc = blade.cc_toolchain.tool('cc')   # 配置阶段已经吸收了 env
cxx = blade.cc_toolchain.tool('cxx')
```

**限制：** `blade.getenv()` 返回的是加载 `BLADE_ROOT` 那一刻的 env 值。两次 run 之间改变 env 本身不会触发增量缓存失效——若依赖 env 驱动的配置做增量正确性判定，需要把相关变量名加到 `global_config.test_related_envs`，或以其它方式纳入配置指纹。

### `blade.cc_toolchain` 对象

> **可用阶段：** 仅 BUILD 阶段

当前平台 C/C++ 工具链的只读代理对象，用于在 BUILD 文件中做出跨平台兼容的判断。

**文件名属性**（均返回 `str`）：

- `obj_suffix`：目标文件后缀（Linux/macOS 为 `.o`，MSVC 为 `.obj`）
- `static_lib_suffix`：静态库后缀（Linux/macOS 为 `.a`，MSVC 为 `.lib`）
- `dynamic_lib_suffix`：动态库后缀（Linux 为 `.so`，macOS 为 `.dylib`，MSVC 为 `.dll`）
- `lib_prefix`：库名前缀（Linux/macOS 为 `lib`，Windows 为 `""`）
- `exe_suffix`：可执行文件后缀（Linux/macOS 为 `""`，Windows 为 `.exe`）

**平台属性**（均返回 `str`）：

- `cc_vendor`：编译器供应商：`'gcc'`、`'clang'` 或 `'unknown'`
- `target_os`：编译目标操作系统：`'darwin'`、`'linux'` 或 `'windows'`。交叉编译时可能与 `blade.host_os` 不同
- `target_arch`：编译目标 CPU 架构：`'x86_64'`、`'aarch64'` 等。交叉编译时可能与 `blade.host_arch` 不同

**工具查询：**

- `tool(key)` → `str | None`：返回由 *key* 指定的工具路径。
  支持的 key：`'cc'`、`'cxx'`、`'ld'`、`'ar'`、`'rc'`、`'as'`。
  工具不可用时返回 `None`（如 Linux 上 `tool('rc')` 返回 `None`）。

**示例：**

```python
cc = blade.cc_toolchain

# 组合输出文件名
obj = src + cc.obj_suffix
static_lib = cc.lib_prefix + 'foo' + cc.static_lib_suffix
binary = 'myapp' + cc.exe_suffix

# 查询工具可用性
if cc.tool('rc'):
    print('Resource compiler:', cc.tool('rc'))

# 根据编译目标平台选择依赖
if cc.target_os == 'linux':
    libs.append('//thirdparty/linux_only:lib')
elif cc.target_os == 'darwin':
    libs.append('//thirdparty/mac_only:lib')

# 构建主机平台（运行构建的机器）
protoc = 'tools/protoc-%s-%s' % (blade.host_os, blade.host_arch)
```

---

## 函数式配置项

配置项的值可以是函数（包括 lambda），在构建阶段延迟求值，以访问仅在 BUILD 阶段可用的 `blade` 属性（如 `cc_toolchain`）。

### 基本用法

```python
cc_test_config(
    # 根据构建类型和编译目标架构动态决定配置项的值
    dynamic_link=lambda blade: not blade.build_type_is_debug() and blade.cc_toolchain.target_arch != 'ppc64le',
    heap_check=lambda blade: 'strict' if blade.cc_toolchain.target_arch != 'aarch64' else '',
)
```

### 限制

- 传入的函数必须接受**恰好 1 个参数**（`blade` 模块），赋值时即检查参数个数
- 函数的返回值类型必须与配置项的默认值类型一致，在求值时检查
- **函数不能和普通值组合在同一列表中**——整个配置项要么是函数，要么是普通值。不支持 `[func, 'value']` 这样的混合列表
- 不支持 `append_` / `prepend_` 前缀与函数结合使用
- 普通函数也可以使用，不限于 lambda：

```python
def my_extra_incs(blade):
    return [
        'thirdparty/',
        'thirdparty/%s/' % blade.cc_toolchain.target_arch,
    ]

cc_config(
    extra_incs=my_extra_incs,
)
```

---

## `build_target` 废弃

`build_target` 已废弃，将在未来版本中移除。请使用以下 `blade.` 替代方式：

| `build_target` | 替代 | 说明 |
| --- | --- | --- |
| `build_target.bits` | `blade.cc_toolchain` (通过 target_arch 推算) | 目标位数，如 32、64。需在 BUILD 阶段通过函数式配置项访问 |
| `build_target.arch` | `blade.cc_toolchain.target_arch` | 目标 CPU 架构 |
| `build_target.os` | `blade.cc_toolchain.target_os` | 目标操作系统 |
| `build_target.is_debug()` | `blade.build_type_is_debug()` | 是否为 debug 构建 |

**迁移示例：**

```python
# 旧写法 (BLADE_ROOT 中)
def get_build_dir():
    return 'build%d_%s' % (
        build_target.bits,
        'debug' if build_target.is_debug() else 'release',
    )

# 新写法
# 配置阶段可用的属性直接用
# 配置阶段不可用的属性（如 cc_toolchain）通过函数式配置项延迟求值
cc_test_config(
    dynamic_link=lambda blade: not blade.build_type_is_debug() and blade.cc_toolchain.target_arch != 'ppc64le',
)
```
