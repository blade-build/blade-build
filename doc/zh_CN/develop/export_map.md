# `export_map`（符号导出控制）实现原理

`export_map` 通过链接器的
[version script](https://sourceware.org/binutils/docs/ld/VERSION.html) 控制一个共
享库/可执行文件导出哪些符号。在 GNU ld 上它被原样透传；在 macOS 与 Windows——它们没
有 `--version-script`——Blade 则*模拟*它。本文讲解它**如何实现**；面向用户的描述见
[build_rules/cc.md](../build_rules/cc.md#控制共享库导出哪些符号)。

涉及的源文件：

| 文件 | 职责 |
| --- | --- |
| `src/blade/cc_targets.py` | `_resolve_linker_input_file`（属性 → 全路径、处理 plural 别名）、`_cc_link`（Linux/macOS 派发）、`_dynamic_cc_library_windows`（DLL `.def` 路径） |
| `src/blade/builtin_tools.py` | `cc_macos_exports`（ld64 列表）与 `cc_windef`（`.def` 过滤） |

---

## 1. 一个属性，三种链接器现实

`export_map` 属性是单个 version-script 文件。其机制是**导出过滤**，而非 ABI 版本化
——名字由此而来（已废弃的复数形式 `version_scripts` 是别名）。三种后端有根本差异：

| 工具链 | 原生支持 | Blade 的做法 |
| --- | --- | --- |
| GNU ld（Linux） | 有（`--version-script`） | 透传 |
| Apple ld64（macOS） | 无 | 翻译为 `-exported_symbols_list` |
| MSVC link.exe（Windows） | 无 | 过滤自动生成的 `.def` |

由于 macOS/Windows 的模拟按**反修饰（demangled）后的名字**工作，两者都有两条限制：
**重载坍缩**（一个名字要么连同所有重载一起导出、要么都不导出），以及带引号的签名模
式（`"f(int)"`）只按其名字部分匹配（并一次性警告）。完整的 ELF version 节点仅
Linux 独有。实践中 `ns::class::method` 形式的模式已足够。

## 2. 属性解析（`_resolve_linker_input_file`）

`export_map` 与已废弃的复数 `version_scripts` 由 `_resolve_linker_input_file` 规范化
为 `export_map_fullpath`（至多一个路径的列表），此函数与 `linker_script` 共用。它：

- 若使用了已废弃的复数形式则警告并回退（两者都给时忽略复数）；
- 若给了多个文件则警告并只保留第一个——GNU ld 拒绝两个匿名 version 节点，单个文件是
  唯一有意义的数量。

保持为单元素列表，使其能直接拼接进现有的 `_cc_link(version_scripts=...)` 处理。

## 3. Linux 与 macOS 派发（`_cc_link`）

`_cc_link` 收到 `version_scripts`，并按目标 OS 分支：

```python
if version_scripts:
    if is_darwin:
        # 翻译为 ld64 的 -exported_symbols_list
        export_map = version_scripts[0]
        exports_list = '%s.exported_symbols_list' % output
        self.generate_build('cc_macos_exports', exports_list,
                            inputs=objs, implicit_deps=[export_map],
                            variables={'export_map': export_map})
        extra_linkflags.append('-Wl,-exported_symbols_list,' + exports_list)
        implicit_deps.append(exports_list)
    else:
        extra_linkflags += ['-Wl,--version-script=%s' % ver for ver in version_scripts]
        implicit_deps += version_scripts
```

- **Linux** —— 发射 `-Wl,--version-script=<file>`，并把脚本加为 implicit dep，使改脚
  本即重链。
- **macOS** —— 先由一条 `cc_macos_exports` rule 把 version script **转换**成 ld64 的
  `-exported_symbols_list` 文件（见 §5），再由链接消费它。

（`_cc_link` 这里也处理 `linker_script`（`-T`）；ld64 无对应物，故警告并丢弃。MSVC
永不到达此分支。）

## 4. Windows DLL 路径（`_dynamic_cc_library_windows`）

MSVC 的导出控制接入**自动导出 `.def`**流水线，而非链接标志。Blade 已经从目标文件生
成 `.def`（`cc_windef`，经 COMDAT 过滤）来导出 DLL 的符号。当设置了 `export_map`
时，同一条 rule 还会把 `.def` **过滤**一遍 version script：

```python
export_map = self.attr.get('export_map_fullpath')
if export_map:
    def_vars = {'defflags': '--export_map=%s' % export_map[0]}
    def_implicit = [export_map[0]]
self.generate_build('cc_windef', def_file, inputs=objs,
                    implicit_deps=def_implicit, variables=def_vars)
```

过滤后的 `.def` 再驱动 DLL 链接（`/DEF:`），于是只有匹配的符号被导出——这对维持在 PE
的 64K 导出上限以内也有用。

## 5. 转换工具（`builtin_tools`）

两种模拟都是"仅按名字反修饰再匹配"，构建期运行：

- **`cc_macos_exports`** —— 用 `nm` 枚举每个 `.o` 的全局符号，用 libc++abi 的
  `__cxa_demangle` 反修饰每个符号，把反修饰名与 version script 的 `global` /
  `local` 模式匹配，并把匹配的（Mach-O 下划线前缀的）修饰名写进 ld64 读取的
  `-exported_symbols_list` 文件。
- **`cc_windef`** —— 在 `.def` 上的同一思路：每个符号的反修饰名
  （`UnDecorateSymbolName` / `undname`）与脚本匹配；不匹配的导出从 `.def` 中删除。

二者共有的特性——*反修饰丢弃重载签名*——正是这两个平台上重载坍缩、签名模式退化为仅按
名字匹配的根本原因。
