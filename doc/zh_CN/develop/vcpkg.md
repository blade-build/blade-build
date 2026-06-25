# vcpkg 支持实现原理

Blade 通过 `vcpkg#<port>:<lib>` 引用把 [vcpkg](https://github.com/microsoft/vcpkg)
库当作一等依赖来消费。本文讲解它**如何实现**
（[issue #1236](https://github.com/blade-build/blade-build/issues/1236)）；面向用户
的指南见 [build_rules/vcpkg.md](../build_rules/vcpkg.md)。

涉及的源文件：

| 文件 | 职责 |
| --- | --- |
| `src/blade/vcpkg.py` | 全部 vcpkg 逻辑：triplet 推导、`.pc`/CMake 解析、manifest/triplet 生成、`vcpkg#` 依赖处理器，以及托管安装编排（`setup`） |
| `src/blade/target.py` | `register_dep_scheme` + `_unify_scheme_dep`——把 `vcpkg#...` 路由到处理器的 `<scheme>#<coordinate>` 派发 |
| `src/blade/cc_targets.py` | `VcpkgLibrary`——自动创建、链接已解析 port 制品的目标 |
| `src/blade/build_manager.py` | `setup_vcpkg()`——在配置加载与 BUILD 解析之间调用 `vcpkg.setup(self)` |
| `src/blade/load_build_files.py` | import `blade.vcpkg`，使 scheme 注册生效 |
| `src/blade/config.py` | `vcpkg_config(...)` schema |

---

## 1. 两个阶段，干净分离

vcpkg 支持的组织方式让**纯粹、可测试的逻辑**能与有副作用的编排分开。`vcpkg.py` 的
模块 docstring 点明了这两者：

- **引用解析**（分析期）：把一个 `vcpkg#port:lib` 字符串变成具体的安装树路径，并为
  它创建一个目标。纯函数加一个处理器。
- **托管安装**（`setup`，构建期）：生成 manifest + overlay triplet 并运行
  `vcpkg install`。唯一大量触碰网络/磁盘的步骤。

模块大部分是对朴素输入的纯函数（`triplet_for`、`parse_pkgconfig`、
`manifest_json`、`port_required_libs` …），可独立单测；有状态的部分
（`_vcpkg_dep_handler`、`setup`）只是从 toolchain/config 收集输入再调用它们的薄包
装。

## 2. `vcpkg#` 引用是一个依赖 *scheme*

`vcpkg` 扩展了 Blade 的 `#name` 系统库家族。形如 `<scheme>#<coordinate>` 的依赖由
`target._unify_scheme_dep` 派发，`vcpkg.py` 在 import 时注册自己：

```python
_blade_target.register_dep_scheme('vcpkg', _vcpkg_dep_handler)
```

这个 import 发生在 `load_build_files.py` 中，所以 scheme 在任何 BUILD 文件被解析之
前就已生效。`#pthread`（无 scheme）仍表示"按名字解析的系统库"；`vcpkg#fmt:fmt` 表
示"通过 vcpkg provider 解析 `fmt:fmt`"。

## 3. 解析：`_vcpkg_dep_handler` → `VcpkgLibrary`

当某目标依赖 `vcpkg#fmt:fmt` 时，`_vcpkg_dep_handler(referrer, 'fmt:fmt')`：

1. **治理** —— 若设置了 `vcpkg_config.direct_use_allowed`，则拒绝来自白名单之外路
   径的引用（呼应大仓常用的 wrapper 库纪律）。
2. **triplet** —— `triplet_for_toolchain(toolchain)` 从 Blade 解析出的工具链推导
   triplet（`x64-linux`、`arm64-osx` …）；`'auto'`/未指定时解析为静态变体（在
   Windows 上即 `-static` triplet，因为 vcpkg 那里默认动态）。
3. **`resolve_reference(...)`** —— 纯验证 + 路径计算：拆分 `port:lib`，强制执行**白
   名单**（`port in packages`，否则硬报错），计算 `lib_dir`（MSVC-ABI debug 构建用
   `debug/lib` 子树，否则 `lib`）与共享的 `include_dir`。`lib == 'hdrs'` 标记
   header-only port。
4. **目标创建** —— 自动创建一个 `VcpkgLibrary`（与 `_add_system_library` 同一套路），
   以 `vcpkg#port:lib` 为 key，因而只创建一次并复用。对托管模式下 `'auto'` 链接的
   port，还会在独立的 `-shared` 安装树里计算*共享*兄弟的 `dynamic_lib_dir`。

`root` / `triplet` 被存放在目标上，使其能**在 generate 期惰性**解析该 port 的
pkg-config 私有系统库与传递性 `Requires:` 兄弟——分析期安装树可能还不存在（安装在两
者之间运行；见 §5）。

## 4. 解析一个 port 真正需要什么

单个 `vcpkg#protobuf:protobuf` 引用必须拉入正确的兄弟归档与系统库。`vcpkg.py` 从安
装树读取这些信息：

- `parse_pkgconfig(text)` 解析 port 的 `.pc` 文件——`Libs` / `Libs.private`（`-l`
  导出与私有系统库）以及 `Requires` / `Requires.private`（兄弟 vcpkg 模块）。
  `_expand` 解析 `${prefix}` 之类的 pkg-config 变量。
- `port_required_libs(...)` 跟随这些 `Requires:` 找到兄弟归档——这正是 protobuf
  （v22+）能透明链接整套 `absl_*` + `utf8_range` 而无需用户逐一列出的原因。
- `port_system_libs(...)` 从 `Libs.private` 与 CMake 链接接口
  （`_cmake_link_libs`）提取 OS/SDK 库。

这些都是纯文本函数，因而很容易用抓取的 `.pc` 夹具做单测。

## 5. 托管安装：`setup`

`build_manager.setup_vcpkg()` 调用 `vcpkg.setup(builder)` 一次，**在配置加载与
analyze 之后、在需要安装制品之前**。关键行为：

- **无需即空操作** —— 除非 `manage=True`（默认）且 `packages` 非空，*并且*
  `_build_uses_vcpkg(builder)` 为真，否则提前返回。这一**按需驱动**的闸门让工作区可
  以无条件声明 `vcpkg_config`（这是固定的项目属性），而一次不引用任何 `vcpkg#...`
  依赖的构建分文不付——也永不需要 vcpkg 工具。
- **overlay triplet** —— 它生成一个 `blade-<triplet>` overlay
  （`overlay_triplet_cmake`），**chainload Blade 解析出的编译器**
  （`chainload_cmake`），使制品与构建其余部分 ABI 兼容。MSVC 是例外：`cl.exe` 用
  vcpkg 原生工具链（不 chainload），由 vcpkg 搭建完整的 MSVC 环境。
- **隔离树** —— manifest（`vcpkg.json`）、chainload cmake 与 overlay triplet 写到
  `<build>/.cache/vcpkg/` 下；`vcpkg install` 安装到那里的 `installed/<overlay>`。
  只有*制品*位于构建目录下；vcpkg *工具*仍通过 `vcpkg_config.root` / `$VCPKG_ROOT`
  / `PATH` 查找（`_find_vcpkg_tool`）。
- **stamp 跳过** —— 对 `(manifest + chainload + triplet_cmake + overlay)` 的 md5
  与 `.blade-vcpkg-stamp` 比对；stamp 未变且 `installed/<overlay>` 已存在则完全跳过
  安装。
- **按需的第二棵（共享）树** —— `_auto_dynamic_ports(builder, packages)` 从已分析的
  图计算出哪些 `'auto'` port 真的被 `dynamic_link` 二进制依赖（`setup` 在 analyze
  之后运行）。只有这些 port 才被第二次安装为共享库到独立的 `-shared` 安装根
  （`_install_shared`）。纯静态构建完全跳过此步。

## 6. 链接模型

`port_options` / `_effective_linkage` 解析 port 的 `linkage`
（`'auto'` / `'static'` / `'dynamic'`）。`'auto'` 默认仿照 `cc_library`：静态归档
始终存在，而共享构建**仅在按需**——当某 `dynamic_link` 二进制依赖该 port 时——才产
生，这就是共享构建落在独立 `blade-<triplet>-shared` 树的原因（vcpkg 每个 triplet 只
构建一种链接方式）。`dynamic_ports` / `auto_ports` 喂给上面的 triplet 与第二次安装
计算。这正是无需逐 port 配置就能避免单例重复问题（gflags/protobuf/… 在所有 dylib 间
只有一份共享实例）的机制。

## 7. 出问题先看哪里

- *解析*问题（路径错、兄弟缺失、白名单消息）→ `resolve_reference` /
  `port_required_libs` / `_vcpkg_dep_handler`。
- *安装*问题（triplet 错、ABI 不匹配、每次都重装）→ `setup` /
  `overlay_triplet_cmake` / `chainload_cmake` / stamp 逻辑。
- *链接*问题（该共享却静态、单例冲突）→ `port_options` / `_effective_linkage` /
  `_auto_dynamic_ports`。
