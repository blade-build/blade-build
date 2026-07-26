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
- `set_variable(name, value, override=False)` 函数：声明一个可供 BUILD 文件读取的构建变量。详见下文 [构建变量](#构建变量)。

### 两个阶段均可用的函数

- `get_variable(name, default=...)` 函数：读取由 `set_variable` 声明的构建变量。在 `BLADE_ROOT` 与 BUILD 文件中**均**可用。详见下文 [构建变量](#构建变量)。

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
- `build_dir` 属性：返回工作空间下的 build 子目录名，比如 `build_release`

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

**为什么只在配置阶段？为什么 BUILD 文件（和 `.bld` 扩展）根本不能读环境变量？** 两个原因,都是为了构建可复现:

1. **可审计。** 如果任意 BUILD 文件都能 `getenv`，影响构建的环境变量就散落在整棵树里、无从知晓。把 env 访问限制在 `BLADE_ROOT`,所有 env 依赖都集中在一个可从头读到尾的文件里。
2. **hermetic + 增量正确。** 一个悄悄按 `$SOMEVAR` 分支的 BUILD 文件,对不同开发者会产出不同的构建图;更糟的是,改这个 env 变量**不会**让缓存的 per-target 构建失效——因为 env 值从未进入构建指纹。你会拿到过期产物却不重建。

所以 BUILD 文件永不直接读环境变量。要让 env 衍生的值影响 BUILD,**在 `BLADE_ROOT` 里把它折进一个构建变量**,再在 BUILD 里读这个变量:

```python
# BLADE_ROOT（配置阶段）：读一次 env，发布成命名变量
blade.set_variable('use_jemalloc', blade.getenv('USE_JEMALLOC', '0'))

# 任意 BUILD 或 *.bld 文件：读变量——绝不读 env
deps = [':core']
if blade.get_variable('use_jemalloc') == '1':
    deps.append('//thirdparty/jemalloc:jemalloc')
```

这样 env 依赖既显式（`BLADE_ROOT` 里一次 `getenv`）**又**增量正确:解析后的变量是配置指纹的一部分,所以 `$USE_JEMALLOC` 变化（或 `--define use_jemalloc=1` 覆盖）会重新生成受影响的 target。详见 [构建变量](#构建变量)。对于 toolchain 字段,也可以直接从 `blade.cc_toolchain.tool('cc')` 读已在配置阶段吸收 env 的值。

### 构建变量

> **可用阶段：** `set_variable` 仅 `BLADE_ROOT` 配置阶段；`get_variable` 在 `BLADE_ROOT` 与 BUILD/`.bld` 中均可用。

构建变量是由 `BLADE_ROOT` 发布、BUILD 文件读取的命名值。它是从环境变量（或任意配置期计算）通向 hermetic BUILD 文件的**唯一受控桥梁**——BUILD 文件本身[不能读环境变量](#bladegetenv)。

```python
def set_variable(name: str, value, override: bool = False) -> None   # 仅 BLADE_ROOT
def get_variable(name: str, default = ...)                           # 两个阶段
```

```python
# BLADE_ROOT：声明变量（来自 env、host 信息，或纯常量）
blade.set_variable('use_jemalloc', blade.getenv('USE_JEMALLOC', '0'))
blade.set_variable('max_shards', 8)

# 任意 BUILD / *.bld：读取
if blade.get_variable('use_jemalloc') == '1':
    deps.append('//thirdparty/jemalloc:jemalloc')
n = blade.get_variable('max_shards')
```

**语义**

- **`set_variable` 仅配置阶段可用。** BUILD 文件只读不声明,在 BUILD 里调用会报错终止。
- **读未声明的变量会报错**,除非传了 `default`。拼错或从未声明的名字会**响亮地失败**,而不是悄悄返回 `None`。用 `default` 让变量可选:`blade.get_variable('opt', 'off')`。
- **重复声明同名会报错**,除非 `override=True`。跨 `include` 的意外重设会被抓住,而不是静默取最后一次的值。有意分层时用 `override=True`（基础配置给默认值,机器特定的 include 覆盖）。
- **值可以是任意类型**(`str`、`int`、`list` ...),不限于字符串。
- **解析后的变量是配置指纹的一部分。** 值变化（无论来自 `set_variable`、喂它的 env、还是 `--define` 覆盖）都会重新生成受影响的 per-target 构建。这正是 env 驱动配置能保证增量正确的原因。

**命令行覆盖:`--define`**

`blade build|test|run -D NAME=VALUE`(可重复)从命令行覆盖一个已声明的变量——方便 CI 固定某个值,或本地临时实验而不改 `BLADE_ROOT`:

```bash
blade build --define use_jemalloc=1 //...
```

`--define` **只能**覆盖 `BLADE_ROOT` 已用 `set_variable` 声明过的变量（覆盖未声明的名字会报错),因此变量命名空间始终只由 `BLADE_ROOT` 定义。`--define` 的值是字符串;若被覆盖的变量原本是非字符串类型,覆盖值按字符串原样生效,因此 `--define` 适用于字符串/标量变量。

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
