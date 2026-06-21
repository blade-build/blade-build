# 升级到 V3 版

## 概述

V3 是一次全面的现代化升级，主要目标是：

- **仅支持 Python 3.10+**，彻底移除 Python 2 和旧版 Python 3 的兼容代码
- **全量类型标注**，所有构建目标模块均已添加 PEP 604 类型注解，通过 pyright 静态检查
- **代码清理**，移除死代码和失效测试，修复已知 bug
- **macOS 支持**，修复了多个 macOS 上的编译兼容性问题
- **构建目录命名现代化**，默认目录去掉遗留的 `64`（`build64_release` → `build_release`），并新增 `${os}`/`${arch}` 模板变量以支持多平台构建

升级到 V3，可以获得这些好处：

- 更可靠的类型安全，减少 BUILD 文件编写时的参数错误
- 完善的单元测试和跨仓库 E2E 冒烟测试覆盖
- 更清晰的代码结构，方便二次开发和扩展
- macOS 上可以直接使用 blade
- 更好的文档覆盖（新增 Go 构建文档、`$(location)` 语法文档）

## 升级常见问题

### Python 版本

V3 **只支持 Python 3.10 及以上版本**（在 3.10 - 3.14 上经过 CI 测试）。V2 支持的 Python 2.7 和旧版 Python 3 不再支持。

如果你的系统默认 Python 版本低于 3.10，可以通过环境变量 `BLADE_PYTHON_INTERPRETER` 指定 Python 解释器：

```bash
# 设置 BLADE_PYTHON_INTERPRETER 环境变量指向 Python 3.10+
export BLADE_PYTHON_INTERPRETER=/usr/bin/python3.12
```

### BUILD 文件语法变更

V3 **完全兼容** V2 的 BUILD 文件语法。所有构建规则（`cc_library`、`cc_binary`、`java_library`、`proto_library` 等）的参数和行为保持一致。

唯一的差异：`fbthrift_library` 已被移除（从未在 ninja 后端实现）。如果你的 BUILD 文件中使用了 `fbthrift_library`，请迁移到 `thrift_library`。

### 已移除的功能

以下功能在 V3 中已被移除：

- **`fbthrift_library`** — 从未在 ninja 后端实现，`generate()` 直接报错。请使用 `thrift_library` 代替。
- **`swig_library`** — 尚未在 ninja 后端实现（已保留规则注册，但构建时报错）。
- **`example/` 目录** — 示例代码已迁移至独立的 [blade-test](https://github.com/blade-build/blade-test) 仓库。
- **`fbthrift_library_config` 配置函数** — 已删除（但 `BLADE_ROOT` 中仍可调用，作为空操作保留）。

### macOS 支持

V3 修复了以下 macOS 兼容性问题：

- `-static-libgcc` / `-static-libstdc++` 不再在 macOS 上使用（clang 不支持这些 GCC 专用标志）
- `--whole-archive` / `--no-whole-archive` 在 macOS 上换用 `-force_load`

macOS 现已作为正式支持的平台。

### 全局配置变更

`BLADE_ROOT` 中的 `blade.conf` 已移除 `fbthrift_library_config` 的调用。如果你的 `BLADE_ROOT` 或 `blade.conf` 中引用了 `fbthrift_library_config`，不会有错误（已保留空操作函数），但建议删除相关配置。

### 扩展和工具

V3 中 `load()` 和 `glob()` 等扩展机制保持不变。以下新增了路径安全校验：

- `gen_rule.outs` 不允许包含 `..`（父目录引用）
- `cc_library.incs` 和 `cc_library.export_incs` 不允许包含 `..`
- `glob()` 的 include 模式中不允许包含 `..`

### 构建目录名

默认构建目录已从 `build64_<profile>` 改名为 `build_<profile>`——例如 `build64_release` → `build_release`。遗留的 `64` 是 32/64 位 multilib 时代的产物，无法区分 `arm64` 与 `x86_64`；平台信息现在来自所选工具链，`global_config.build_path_template` 也新增了 `${os}`/`${arch}` 变量，供需要构建多个平台的项目使用：

```python
global_config(build_path_template = 'build_${os}_${arch}_${profile}')
# build_linux_x86_64_release, build_darwin_arm64_release, ...
```

这是唯一带有一次性成本的变更：

- 旧的 `build64_*` 目录会失效（一次重新构建到新的 `build_*` 目录）。当 blade 在新目录旁发现遗留的 `build64_*` 时会打印一次提示；你可以择机删除旧目录。
- 将 `.gitignore`、CI 缓存键以及引用了 `build64_*` 的脚本更新为 `build_*`（或同时覆盖两者的通配）。
- **若要保留旧名称**，在 `BLADE_ROOT` 中固定模板即可——它会逐字复现 v2 的布局：

```python
global_config(build_path_template = 'build${bits}_${profile}')   # -> build64_release
```

遗留的 `-m32`/`-m64` 选项同样已废弃（它是 x86 multilib 选择器）；请改为选择 arch 为 32/64 位的工具链——由工具链决定 `${arch}`/`${bits}`。

## V2 → V3 升级步骤

1. **升级 Python 环境**：确保 Python 3.10+ 可用，并设置为 blade 的默认解释器。
2. **更新 blade 自身**：拉取 `master` 分支代码，或 checkout 最新 v3 tag（如 `v3.0.0-beta`）。
3. **检查 BUILD 文件**：如有 `fbthrift_library` 引用，改为 `thrift_library`。
4. **检查 BLADE_ROOT**：移除 `fbthrift_library_config` 调用（非必须，建议清理）。
5. **验证编译器**：macOS 用户确认 clang 可用；Linux 用户确认 GCC 或 clang 可用。
6. **构建目录改名**：默认构建目录现在是 `build_<profile>`（原为 `build64_<profile>`）；请更新 `.gitignore` / CI 缓存键 / 脚本，或固定 `build_path_template = 'build${bits}_${profile}'` 以保留旧名称。
7. **运行构建**：`blade build ...` 验证项目可正常编译。

如有问题，请提交 [issue](https://github.com/blade-build/blade-build/issues)。
