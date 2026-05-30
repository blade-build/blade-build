# Visibility 是如何实现与执行的

Visibility 限制谁可以依赖某个 target。blade 把每个 target 的"允许调用
方"集合存为一小组规范化 pattern，在依赖分析阶段对每条 dep 边做一次检
查——一次构建一次，不是运行时。

| 文件 | 作用 |
| --- | --- |
| `src/blade/target.py` | `_init_visibility`、`_check_visibility`、`_match_visibility` |
| `src/blade/target_pattern.py` | pattern 字符串的 `normalize`、`match` |
| `src/blade/dependency_analyzer.py` | 在分析期驱动 per-edge 检查 |
| `src/blade/config.py` | `global_config.default_visibility`、`legacy_public_targets` |

## 1. 属性形态与默认值

`visibility` 接受：

- `'PUBLIC'` 或 `['PUBLIC']`——全局可见。
- 显式 target pattern 列表：`['//path:target', ':sibling',
  '//path:*', '//path/...']`。
- `[]`——只对定义它的 BUILD 文件可见。
- `None`（不写）——回退默认值（见下文）。

不写 `visibility` 时的解析：

1. 若 target 的键出现在 `global_config.legacy_public_targets`，按
   `{'PUBLIC'}` 处理。这是过去把所有东西默认为 public 的项目的迁移
   坡。
2. 否则用 `global_config.default_visibility`，它本身默认空集合（私
   有）。Blade 2.0+ 把私有定为默认；`legacy_public_targets` 是按
   target 保留旧行为的显式开关，便于项目逐步审计。

`target._visibility` 是真正被检查时查询的归一化集合。
`_visibility_is_default` 仅记录用户是否显式写了 `visibility=`——只用于
让诊断更清晰（"默认为私有，详见文档"）。

## 2. 归一化

`_init_visibility()` 把每个 pattern 过一遍
`target_pattern.normalize(v, self.path)`：

- `'//foo:bar'` → `'foo:bar'`
- `':sibling'` → `'<当前 path>:sibling'`（当前 BUILD 所在包）
- `'//foo:*'` → `'foo:*'`（`foo/` 下全部）
- `'//foo/...'` → `'foo:...'`（`foo/` 下递归全部）

`'PUBLIC'` 当哨兵原样存储；不再做其它归一化。结果是 `set[str]`——小、
可哈希、查起来便宜。

## 3. 执行：何时、何地

检查在 `dependency_analyzer.analyze_deps()` 中、deps 展开后做一次。对
每条直接边 `A -> B`，`_check_visibility(A, B)` 求
`_match_visibility(A, B)`：

1. **同包？** `A.path == B.path` 则通过。共享一个 BUILD 的 target 之
   间始终互相可见——"明确知道自己在做什么"的最小单位。
2. **B 的集合里有 `'PUBLIC'`？** 通过。
3. **B 的集合里有精确键 A.key？** 通过。
4. **pattern 命中？** 遍历 pattern，
   `target_pattern.match(A.key, p)` 处理 `:*` 与 `:...` 通配。命中则
   通过。

均不命中则报错：

```
<A 的源位置>: error: <A>: Not allowed to depend on "//<B>"
                          because of its visibility,
<B 的源位置>: info: which is declared here
```

若 B 的 visibility 是默认私有，诊断会再加一句"No explicit 'visibility'
declaration, defaults to private"——这是用户最易困惑的情形。

代价是 O(deps × patterns)。实践中 visibility 集合很小（通常 1–3
个），匹配是集合成员检查 + 短迭代，不需要缓存。

## 4. 特例与豁免

- **同包 target 完全绕过 visibility。** 这条规则让 `cc_test` 能访问同
  包姊妹库的私有内部，而无需 per-test 豁免——同处一个 BUILD，检查本来
  就是 no-op。
- **系统库**（`#dl`、`#pthread`…）构造时把 `visibility=['PUBLIC']`
  写死，总是可达。
- **隐式依赖**（自动注入 `cc_test` 的 gtest、SCM stamp…）经
  `_add_implicit_library` 加入，进入普通 deps 列表。它们**不**豁免；
  隐式 dep 库仍需有合适的可见性，否则每次构建注入就会静默失败。实践
  中这些库按惯例为 `PUBLIC`。
- **prebuilt 与 foreign cc 库**走标准机制——无特例路径。
- **未加载的 target 不检查。** 惰性 BUILD 加载使工作区里那些被请求集
  合够不到的受限 target 不会被审视。这是 by design：分析只在被构建闭
  包上跑。

## 5. 技术细节与用户体验优化

- **2.0 起默认私有**，加上 `legacy_public_targets` 迁移坡。这种改动很
  难在大型 monorepo 一夜推完；坡度允许项目按 target 逐步翻转，而非一
  次性转换全部。
- **`':...'` 递归 pattern 走字符串前缀匹配，不走遍历 target 树。** 便
  宜（一次前缀比较），且因 target 键早就归一化为 `<path>:<name>` 而准
  确。
- **诊断带两端。** 失败既指 A 的 BUILD 行（dep 声明处），又指 B 的
  BUILD 行（visibility 声明处）。用户不必在文件间反复跳。
- **未做匹配结果缓存。** 检查一次分析一次，pattern 简单；加缓存只增代
  码不节省时间。若套件长大，缓存就是个一句话的 `(A.key,
  frozenset(B._visibility))` 字典。
- **同包豁免是最常用的隐式规则。** 这是为什么很多 BUILD 完全不写
  `visibility=`：需要互通的 target 是兄弟、同包规则就让它们工作而无需
  声明。只有外部包要进来时 visibility 才登场。
- **Visibility 是强制，不是过滤。** blade 不把被禁的 dep 从图里偷偷去
  掉；它报错并停下来。这是刻意的——静默忽略会掩盖真实 bug（比如
  `deps` 拼写错误看起来"像是库被藏起来了"）。
