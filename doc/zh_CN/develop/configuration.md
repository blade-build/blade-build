# 配置项是如何加载、分层与读取的

Blade 的配置系统是**分层**的：先是代码里的默认值，再叠加位于若干约定位置
的配置文件，最后是命令行选项对特定项的覆盖。所有内容都进入同一份内存中
的存储，供其它模块读取。

| 文件 | 作用 |
| --- | --- |
| `src/blade/config.py` | 模板（schema）、加载顺序、`cc_config()` / `cc_library_config()` 等的注册 |
| `src/blade/main.py` | 在已加载的配置之上拼接 CLI 选项 |
| `src/blade/command_line.py` | 参与覆盖步骤的 CLI 选项 |

## 1. 层次与优先级

`config.load_files()` 按固定顺序加载各层配置；每一层都**更新**同一份内存
存储，逐项**后写覆盖**。某项如未被后一层提及，就保留之前的值（不是"用
当前层、否则什么都不要"那种覆盖语义）。

1. **Schema 默认值** —— `config.py` 中的 `_CONFIG_TEMPLATE` 是 section
   名、item 名以及内置默认值的权威来源。其中还存放 `__help__` 元数据，
   供 `blade dump` 使用。
2. **`blade.conf`**（位于 blade 入口同目录）—— 一份 blade 安装的站点默认，
   常用于基线 warnings、默认库路径等。
3. **`~/.bladerc`** —— 用户级默认，跨工作区持久。
4. **`BLADE_ROOT`**（工作区根）—— 工作区级配置，同时也是工作区的标识；
   blade 从当前目录向上查找它。
5. **`BLADE_ROOT.local`** —— 单个 checkout / 单个开发者在 `BLADE_ROOT` 之
   上的本地覆盖。仅当 `--load-local-config` 打开（默认开）时加载。
6. **CLI 选项回写** —— 在 `main.py` 末尾，`adjust_config_by_options()` 把
   一小部分白名单 CLI 选项（如 `--build-jobs`、`--debug-info-level`）翻译
   回 config 调用，落到同一份存储里，语义和写在 `BLADE_ROOT` 中一致。其
   它选项（`--coverage`、`--profile`、`--gprof` 等）由各自的消费者直接
   读取解析后的 `options` 对象。

所有已加载配置文本的累计哈希通过 `config.digest()` 暴露，并折叠进每个
target 的 fingerprint 中，所以任何配置变化都能定向地让相关 target 的缓存
ninja 失效（见[依赖分析与 ninja 生成](dependency_analysis.md)）。

## 2. Schema 与 `@config_rule` 装饰器

每一个可以在配置文件里调用的 section（`global_config`、`cc_config`、
`cc_library_config`、`proto_library_config`、`cc_toolchain_config`、…）都
是 `config.py` 中一个用 `@config_rule` 装饰的普通 Python 函数。该装饰器
把函数注册进 `_config_globals` —— 那是 `exec()` 配置文件时使用的命名空
间。所以**有效的 section 名集合就是 `@config_rule` 函数集合**。

每个规则函数体内调用 `_blade_config.update_config(section, append, kwargs)`，
合并进 section 的字典。支持三种赋值形式：

- **直接替换**（`cc_config(cppflags=[...])`）—— 覆盖该 item。
- **按项追加**（`cc_config(append_cppflags=[...])`）—— 对 list/set 型 item
  采用 `+=` 语义；同一次调用里同时给 `cppflags` 和 `append_cppflags` 会
  报错。
- **`append=` 参数** —— 老式写法，仍可用但会在诊断中标为 deprecated；推
  荐使用按项的 `append_<name>` 形式。

多实例 section（如 `cc_toolchain_config`，可用不同名字多次调用）在 schema
中以空 dict 起步，由对应的 `@config_rule` 按 key 逐项填充。

### 类型检查

item 的类型由 schema 默认值推得 —— `_assign_item_value` 用
`isinstance(value, type(section[name]))` 比对该 item 的当前值，并做两类
归一化：当 schema 是 list 时把 `str`（或 `var_to_list` 接受的形态）转
成 `list[str]`，当 schema 是 set 时转成 `set`。标量 item 的类型不对是
**致命错误**，错误信息会同时给出期望与实际类型，用户在配置文件那一行就
看到 `Incorrect type for "cppflags", expect "list", actual "str"`，而不
是某个 target 编译期出错时才察觉。

当"满足 schema 类型"还不够时，特定的 `@config_rule` 体内会叠加**枚举
校验**：`_check_kwarg_enum_value(kwargs, 'debug_info_level', valid_values)`。
`hdr_dep_missing_severity`、`heap_check`、`duplicated_source_action`、
`cc_toolchain.kind` 等就是用这种方式收窄取值集合。校验在
`update_config` 之前完成，非法值不会落到内存存储里。

## 3. 运行时读取与延后求值的 callable

其它代码通过两个函数读 config：

- `config.get_section(name)` 返回 `_ConfigSectionView` —— 一个薄薄的、按访
  问惰性解析的 dict-like 包装。
- `config.get_item(section, item)` 是单项的便捷形式。

**为什么支持 callable 形式。** 少数 config 项需要参考 `BLADE_ROOT` 解
析时还不存在的**构建上下文**——主要就是**工具链**。典型场景是**多编译
器配置与选择**：工作区可能注册多个不同名字的 `cc_toolchain_config(...)`，
然后让 `cc_config` 里某些 item 按最终选定的工具链分支（如 clang 与
msvc 用不同 cppflags、或者从工具链拿出 C++ 标准）。这个选择在配置文件
解析时还没定，依赖 CLI 标志和宿主检测。所以 blade 允许你把值写成 lambda，
入参就是活的 `blade` 模块：

```python
cc_config(
    cppflags = lambda blade: ['-std=c++17']
              if blade.cc_toolchain.cc_vendor != 'msvc'
              else ['/std:c++17'],
)
```

解析期 `_assign_item_value` 看见是 callable，先用
`_check_callable_arity` 校验它恰好接受一个参数，再把它包成
`_DeferredConfigValue`，同时**从 schema 默认值推断并记下期望的返回类
型**。section 字典里坐的是这个包装对象，函数本身**此刻尚未被调用**。

查询期 `_resolve_value()` 用活的 `blade` 模块调用该函数，并把返回值与记
下的 `expected_type` 再核对一次。类型不符会清晰地报告 "function for X
returned Y, expected Z"，而不是让一个类型错的值流向下游。一个例外：
`blade dump --config` 时 build manager 还未初始化，延后 callable 会原
样返回，让 dump 仍能完成。

反复读取同一 config 项的 target（例如 `cc_targets.py` 里的
`PrebuiltCcLibrary._default_libpath`）会把首次解析的结果缓存到类属性上，
避免重复求值。

## 4. 技术细节

- **CLI 选项回写刻意收窄。** 只有"语义等同于某个 config 项"的选项才走
  `adjust_config_by_options()`。改变构建模式的选项（`--coverage`、
  `--profile`、`--gprof`、`--profile-generate/use`）则以普通属性挂在
  `options` 对象上，由各自消费者读取。这样"调节构建"（旋钮）和"在做什
  么样的构建"（命令）保持分离。
- **配置文件的沙箱。** 配置文件用受限的 globals（只有 `_config_globals`
  集合 + 一个 deprecated 的 `build_target` 兼容垫片）来 `exec`，没有完
  整的 Python builtins。所以配置文件不是任意 Python 脚本，而是一串平铺
  的 `<section>_config(...)` 调用。
- **平台条件规则。** `msvc_config()` 在非 Windows 主机上是空操作，方便跨
  平台的 `BLADE_ROOT` 无条件包含它，不影响 Linux/macOS。schema 仍带 MSVC
  各项，使得 `blade dump` 在所有平台上都能产出完整的规范化配置。
- **`config.digest()` 作为熵源。** 全部已加载配置文本的 MD5 是每个 target
  fingerprint 的一部分。改了 `BLADE_ROOT` 之后，正好会让需要重生成 ninja
  的那些 target 的缓存失效，其它模块无需另行追踪配置变化。
- **`blade dump` 是 schema 的反向输出。** 它走一遍 `_CONFIG_TEMPLATE`，
  把每一项（含 deferred 可调用对象）都解析出来，写成一份能再次被加载的
  规范化配置文件。也是"有哪些 item、当前值是什么"的权威来源。
