# `gen_rule`：自定义构建步骤与其它 target 如何感知它

`gen_rule` 让 BUILD 跑任意 shell 命令并声明其输出。有意思的不是规则本
身——而是这些输出**怎样不显式注解就变成其它 target 的一等输入**。

| 文件 | 作用 |
| --- | --- |
| `src/blade/gen_rule_target.py` | `GenRule` 类、属性校验、`cmd` 替换 |
| `src/blade/target.py` | `_target_file_path()`（输出所在位置） |
| `src/blade/cc_targets.py` | `srcs`/`hdrs` 中自动识别 gen_rule 输出 |

## 1. 属性与 `cmd` 替换

```python
gen_rule(
    name = 'codegen',
    srcs = ['schema.idl'],
    outs = ['schema.h', 'schema.cc'],
    cmd  = '$TOOL --in=$FIRST_SRC --out-dir=$OUT_DIR',
    deps = ['//tools:my_codegen'],
    generated_hdrs = ['schema.h'],   # 可选；不写则从 outs 推断
)
```

- `outs` 必填；条目按包路径归一化，禁止 `..`（不能跳出构建目录）。
- `cmd` 是模板，在 ninja 生成期展开。替换变量：
  - `$SRCS` / `$OUTS`——所有输入/输出（即 ninja 的 `${in}`/`${out}`）。
  - `$FIRST_SRC` / `$FIRST_OUT`——第一个输入/输出，以 per-edge ninja 变
    量暴露，单输入/单输出工具无需自己拼列表。
  - `$SRC_DIR`——源包路径。
  - `$OUT_DIR`——`build_dir/<pkg>`（输出落点）。
  - `$BUILD_DIR`——工作区构建根目录。
  - `$(location //pkg:target)`——解析为指定 target 的输出文件路径。这
    是 gen_rule 跨 target 引用另一个 target 生成物的正确方式。
- `generated_hdrs`（可选）：哪些输出按 header 处理（影响可见性）；不写
  则按文件后缀推断。
- `generated_incs`（可选）：要加进消费者 include 路径的目录——适合产出
  一棵头文件树、消费者按子路径 `#include` 的代码生成器。

## 2. Ninja 生成

每个 `gen_rule` 声明**自己**的 ninja 规则（不共享通用 `gen_rule` 规
则）。规则名由 target 键派生；模板末尾附 `ls ${out} > /dev/null` 检查，
让"命令静默没产出声明的文件"立即被发现，而不是下游引用缺文件时才报。

输出经由 `_target_file_path()` 落到 `build_dir/<pkg>/<outname>`，这是
唯一的路径构造路径；没有写到源树的方式。这是设计上的强约束——`gen_rule`
从来不接受源相对的输出路径。

POSIX 上命令经 `/bin/sh` 运行（CWD 是工作区，路径按工作区相对）。需要
Windows 专属命令的用户自己写得当；blade 不试图把 `/bin/sh` 语义翻译成
`cmd.exe`。

## 3. 其它 target 如何感知输出

关键是**自动发现**：在 `srcs` 里列 `schema.cc` 的 `cc_library` 无需对
`codegen` target 声明依赖。`cc_targets._cc_objects()`（以及其它消费方）
走 `srcs` 时，源树里不存在的条目就当作生成文件，反查产出它的 target 的
`_target_file_path()`，dep 边隐式补上。

生成头进一步：

- `gen_rule.generated_hdrs` / `generated_incs` 注册进与
  `declare_hdrs()` / `declare_hdr_dir()` 共享的全局 map，
  [hdrs check](hdrs_check.md) 因此知道头文件的归属 target。
- 消费者的 `declared_genhdrs` 与 `declared_genincs` 通过遍历
  `expanded_deps` 收集每个 dep 的生成头声明而填充。这就是包含检查需要
  的传递性可见性。
- 生成头作为 **order-only dep（`||`）** 出现在编译里，保证它存在于编
  译之前，但 mtime 变化不重新触发编译。

四者合在一起（`-Ibuild_dir`、`srcs` 中自动识别、生成头声明、order-only
dep）才完整实现了"gen_rule 在消费者眼里就跟普通源一样"。

## 4. 技术细节与用户体验优化

- **`ls ${out}` 检查是兜底。** 它能识别用户 `cmd` 不小心把输出写到了与
  `outs` 不同的文件名、或静默失败的情况。没它的话，下游就只能看到"找
  不到文件"那种难追的错误。
- **源树按构造保持干净。** 因为输出永远在 `build_dir/<pkg>/` 之下，
  gen_rule 不能污染源树。这是用户少一项需要学的规则。
- **order-only + `restat` 互配良好。** 如果 gen_rule 输出与上次构建字
  节相同（输入相同重生成产出相同），生产者规则的 ninja `restat` 保留
  mtime，order-only dep 不会强迫下游重编。配合类 `write_if_changed` 工
  具，no-op codegen 路径几乎零代价。
- **`$(location //pkg:target)` 是引用其它生成器的规范方式。** ninja 生
  成期解析路径，与生产 target 在树里的位置无关；在 `cmd` 里硬编码
  `build64_release/...` 路径很脆弱。
- **生成头可见性与 proto 共用机制。** 产出 `.h` 的 gen_rule 通过与
  proto target 相同的路径注册，[hdrs check](hdrs_check.md) 统一处理；
  不必再维护第二条路径。
- **自动发现的一个 caveat。** 同包下两个 gen_rule 产出同名文件，自动
  发现会有歧义；显式在 `deps` 里列产生方可解决。识别该歧义的是与他处
  共用的 per-key 唯一性检查。
- **错误报告标出 gen_rule target 名。** 命令失败来自底层 shell，但
  blade 会以 target fullname 与描述（默认 `COMMAND`）作前缀，便于在大
  量并行构建输出里 grep "哪个 gen_rule 失败了"。
