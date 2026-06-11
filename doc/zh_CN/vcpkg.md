# 使用 vcpkg 包

Blade 可以把 [vcpkg](https://github.com/microsoft/vcpkg)（微软的跨平台 C/C++
包管理器，约 2500 个 port）中的库作为一等依赖直接使用，与源码目标、系统库并列。
在目标的 `deps` 中用 `vcpkg#<port>:<lib>` 引用，在 `BLADE_ROOT` 中一次性声明允许
的包，其余的安装与链接交给 Blade。

这样可以在 Linux、macOS、Windows 上统一管理第三方依赖，省去大量逐包编写
`cmake_build` 的样板代码。

## 快速上手

1. **准备 vcpkg。** 克隆并 bootstrap，然后设置 `VCPKG_ROOT` 或把 `vcpkg`
   可执行文件放进 `PATH`：

   ```bash
   git clone https://github.com/microsoft/vcpkg.git ~/vcpkg
   ~/vcpkg/bootstrap-vcpkg.sh        # Windows 上是 bootstrap-vcpkg.bat
   export VCPKG_ROOT=~/vcpkg
   ```

2. **在 `BLADE_ROOT` 中声明允许的包**：

   ```python
   vcpkg_config(
       baseline = '2024-12-15',          # 固定 ports 树（推荐）
       packages = {
           'fmt': '10.2.1',
           'openssl': '3.2.1',
       },
   )
   ```

3. **用 `vcpkg#<port>:<lib>` 声明依赖**：

   ```python
   cc_binary(
       name = 'app',
       srcs = ['app.cc'],
       deps = [
           'vcpkg#fmt:fmt',
           'vcpkg#openssl:ssl',
       ],
   )
   ```

4. **构建。** 默认情况下 Blade 会安装所声明的包并完成链接：

   ```bash
   blade build //:app
   ```

## 引用语法：`vcpkg#<port>:<lib>`

vcpkg 依赖是 Blade `#name` 系统库家族的扩展。`#` 本就表示“不在本工作区从源码
构建的库”（`#pthread`、`#dl`）；在 `#` 前加一个 scheme 表示这个库来自哪里——这里
是 `vcpkg`。`#` 之后是包管理器自身的坐标。

| 引用形式 | 含义 |
|---|---|
| `vcpkg#<port>:<lib>` | 某个具体静态库——`lib<lib>.a`（`lib` 前缀隐含）。 |
| `vcpkg#<port>:hdrs` | 仅头文件的 port——只暴露 include 目录，不链接归档。 |
| `vcpkg#<port>` | **报错**——port 之后必须指明库名。 |

引用始终是完全显式的：没有“一个 port 的全部库”的简写，因此多库 port 不会被
意外过度链接。

库的 basename 可能与 port 名不同——vcpkg 的 `boost-filesystem` port 产出
`libboost_filesystem.a`，因此引用为 `vcpkg#boost-filesystem:boost_filesystem`。

## 包白名单

`vcpkg_config(packages=...)` 是“哪些 port 可被引用”的唯一事实来源。引用未列出的
port 是**硬错误**——这样所有外部依赖都集中声明、统一管理版本。每个值是版本字符串，
或带 `version` 和/或 `features` 的字典：

```python
vcpkg_config(
    packages = {
        'fmt': '10.2.1',                                   # 简写
        'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']},
    },
)
```

## 托管与非托管安装

`vcpkg_config(manage=...)` 决定由谁来执行 `vcpkg install`。

### 托管（`manage=True`，默认）

由 Blade 替你驱动 vcpkg。在加载 BUILD 文件之前，Blade 会根据白名单生成 manifest，
并用一个 *overlay triplet*（`blade-<triplet>`）把 `vcpkg install` 安装到构建目录下
的隔离目录（`<build>/.cache/vcpkg/`）中；该 overlay 会 chainload Blade 解析出的
编译器，使产物与项目其余部分 ABI 兼容。结果可复现、无需手动步骤——直接
`blade build` 即可。当相关输入没有变化时会跳过安装。

注意 `vcpkg` **工具**仍通过 `vcpkg_config.root`、`$VCPKG_ROOT` 或 `PATH` 定位；
只有安装产物落在构建目录下。

### 非托管（`manage=False`）

由你自己执行 `vcpkg install`，Blade 只从既有安装树
`<root>/installed/<triplet>/` 解析路径，其中 `<root>` 为 `vcpkg_config.root` 或
`$VCPKG_ROOT`：

```bash
vcpkg install fmt openssl          # 自己安装
```
```python
vcpkg_config(manage = False, packages = {'fmt': '10.2.1', 'openssl': '3.2.1'})
```

## 多库 port

`openssl`、`protobuf`、`icu` 等 port 会产出多个归档。每个都是独立目标，按需声明：

```python
deps = [
    'vcpkg#openssl:ssl',         # libssl.a
    'vcpkg#openssl:crypto',      # libcrypto.a
]
```

裸写 `vcpkg#openssl` 会被拒绝，因此不会拉入用不到的库。

## 仅头文件 port

仅头文件的 port 用 `:hdrs` 哨兵——Blade 暴露 include 目录，不链接任何归档：

```python
deps = ['vcpkg#nlohmann-json:hdrs']
```

## 查看有哪些 port 及 port 提供哪些库

### 某个 baseline 下有哪些 port、版本是什么

可用的 port 及其默认版本由 `baseline`（对应 ports 树的某次提交）决定。查看方式：

```bash
vcpkg search            # ports 树中的所有 port 及其版本
vcpkg search fmt        # 名称/描述匹配 "fmt" 的 port
```

`vcpkg search` 反映的是 ports 树当前检出的状态。要查看某个具体 `baseline`，先把
vcpkg 仓库检出到该提交（`git -C $VCPKG_ROOT checkout <baseline>`），或直接读版本
数据库：

- `$VCPKG_ROOT/versions/baseline.json`——每个 port 在 baseline 下的版本。
- `$VCPKG_ROOT/versions/<x->/<port>.json`——某个 port 发布过的所有版本。
- `$VCPKG_ROOT/ports/<port>/vcpkg.json`——该 port 的版本、可用 `features` 及其
  自身依赖。

### 某个 port 提供哪些库

`vcpkg#<port>:<lib>` 引用的是归档 `lib<lib>.a`，其 basename 可能与 port 名不同
（`boost-filesystem` → `libboost_filesystem.a`；`openssl` → `libssl.a` +
`libcrypto.a`）。从安装树里读取确切的库名：

```bash
# 托管模式（manage=True）：在构建目录下，使用 blade- overlay triplet
ls build64_release/.cache/vcpkg/installed/blade-<triplet>/lib/lib*.a

# 非托管模式（manage=False）：在 vcpkg 根目录下
ls $VCPKG_ROOT/installed/<triplet>/lib/lib*.a
```

每个 `lib<name>.a` 都以 `vcpkg#<port>:<name>` 引用。另有两个来源：

- `…/installed/<triplet>/lib/pkgconfig/<pkg>.pc`——`Libs:` 行列出该 port 导出的
  `-l<name>`。
- `…/installed/<triplet>/share/<port>/usage`——vcpkg 给出的可读用法提示，通常会
  列出该 port 提供的库 / CMake target。

某个 port 安装的完整文件清单（含每个 `lib/*.a`）在
`…/installed/vcpkg/info/<port>_<version>_<triplet>.list`。仅头文件的 port 不会
安装任何 `lib*.a`——用 `vcpkg#<port>:hdrs` 引用。

## 版本管理与可复现性

vcpkg 的版本模型是按工作区的（每个包一个版本、一组 features），`vcpkg_config`
直接映射到它：

| `vcpkg_config` 字段 | vcpkg manifest 字段 |
|---|---|
| `baseline` | `builtin-baseline` |
| `packages[pkg]` 版本 | `overrides[].version` |
| `packages[pkg]['features']` | `dependencies[].features` |
| `registries` | `registries[]`（私有 registry） |

为了可复现，把 `baseline` 固定到某个 ports 树提交（日期或 git SHA）；把每个声明的
包都固定到版本可获得最强保证。Blade 会把整个白名单一起安装，保持集合一致。

## Triplet

triplet 默认根据 Blade 的工具链自动推导（`x64-linux`、`arm64-osx`、
`x64-windows-static` 等）。托管模式下 Blade 使用 chainload 编译器的
`blade-<triplet>` overlay。需要指定时用 `vcpkg_config(triplet='...')` 覆盖。

## 大型仓库的封装

如果你的仓库已经通过 `//third_party/` 层统一管理第三方代码，可以把 `vcpkg#`
引用藏在普通 `cc_library` 封装之后，业务代码不直接接触：

```python
# //third_party/openssl/BUILD
cc_library(name='ssl',    deps=['vcpkg#openssl:ssl'],    visibility='PUBLIC')
cc_library(name='crypto', deps=['vcpkg#openssl:crypto'], visibility='PUBLIC')

# //services/payment/BUILD
cc_library(name='payment', srcs=['payment.cc'], deps=['//third_party/openssl:ssl'])
```

## 配置参考

所有设置都在 `BLADE_ROOT` 的 `vcpkg_config(...)` 中。完整字段（`manage`、
`baseline`、`packages`、`registries`、`root`、`triplet`、`install_dir`、
`binary_cache`、`direct_use_allowed`）见配置手册的
[`vcpkg_config`](config.md#vcpkg_config) 一节。

## 排错

- **`vcpkg port "X" is not in the vcpkg_config.packages whitelist`**——把该 port
  加入 `vcpkg_config(packages=...)`。
- **`the vcpkg tool was not found`**（托管模式）——设置
  `vcpkg_config(root=...)`、`$VCPKG_ROOT`，或把 `vcpkg` 放进 `PATH`。
- **`static library not found at ...`**——安装树里没有该库的归档。检查库
  basename（可能与 port 名不同），非托管模式下确认对同一 triplet 跑过
  `vcpkg install`。
- **`a port must name a library`**——引用缺少 `:lib`；用 `vcpkg#<port>:<lib>`
  （或 `vcpkg#<port>:hdrs`）。
