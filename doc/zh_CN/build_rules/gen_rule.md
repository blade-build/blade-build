# 自定义规则构建

## gen\_rule

> **Windows 说明。** `cmd` 由宿主默认 shell 执行（POSIX 上是 `/bin/sh`，Windows 上是
> `cmd.exe`），所以按 `sh` 写的 `cmd` 在 Windows 上不工作。跨平台请用 `cmd_bat`（`cmd.exe`
> 命令）和/或 `cmd_bash`（`bash` 命令）——会按平台自动选择。blade 自身的输出存在性检查已跨平台。
>
> gen_rule 的命令应尽量简单。稍复杂的逻辑,建议写一个小 Python 脚本来调用
> （`cmd = 'python $SRC_DIR/gen.py $SRCS $OUTS'`）：Python 在各平台都在 `PATH` 上,
> 天然跨平台、易调试,也免去各 shell 的引号转义。

用于定制自己的构建规则，参数：

- src_exts: list(str) `src` 里允许的文件扩展名列表。

  不含 `.`，比如 `['m4']` 可以匹配 `config.m4`，如果为空则表示允许所有类型的文件。注意空字符串匹配无扩展名的文件，比如 `['h', '']` 匹配 `vector.h` 和 `vector`。
- `outs`: list，输出的文件列表
- `cmd`: str，被调用的命令行。

  可含有如下变量，运行前会被替换为实际的值：
  - $SRCS 空格分开的源文件名列表，相对 WORKSPACE
  - $OUTS 空格分开的输出文件列表，相对 WORKSPACE
  - $SRC\_DIR 输入文件所在的目录
  - $OUT\_DIR 输出文件所在的目录
  - $FIRST\_SRC 第一个输入文件的路径
  - $FIRST\_OUT 第一个输出文件的路径
  - $BUILD\_DIR 输出的根目录，比如 build[64,32]\_[release,debug]
  - `$(location target)` 和 `$(location target label)` — 被替换为所引用目标的输出文件路径。可选的 `label` 参数指定特定输出（如 `$(location //bin:server bin)` 表示可执行文件）。常用于 `gen_rule.cmd`、`testdata`、`package`、`sh_test` 等场景。示例：

    ```python
    gen_rule(
        name = 'copy_binary',
        cmd = 'cp $(location //server:server) $OUT_DIR/server',
        outs = ['server'],
    )
    ```

- `cmd_bash`: str，通过 `bash` 执行的命令（带 `set -e -o pipefail`）。POSIX 上优先,Windows 上当
  `bash` 在 `PATH`（如 Git Bash）时也用。变量同 `cmd`。
- `cmd_bat`: str，通过 `cmd.exe /S /E:ON /V:ON /D /c` 执行的 Windows 批处理命令。Windows 上优先。变量同 `cmd`。
  `cmd` / `cmd_bash` / `cmd_bat` 至少要设一个;按平台自动选（Windows：`cmd_bat` → `cmd_bash` → `cmd`；
  POSIX：`cmd_bash` → `cmd`）。
- `cmd_name`: str，命令的名字，用于简略模式下显示，默认为 `COMMAND`
- generate\_hdrs bool，指示这个目标是否会生成 outs 里列出的文件名之外的 C/C++ 头文件。
  如果一个 C/C++ 目标依赖会生成头文件的 gen\_rule 目标，那么需要这些头文件生成后才能开始编译。
  gen\_rule 会自动分析 outs 里是否有头文件，就不需要设置。
  此选项会降低编译的并行度，因为如果一个目标如果可以分为生成源代码（其中包含头文件）和编译以及生成库
  三个阶段，那么精确给出头文件列表时，在第一阶段的头文件生成后，其他的目标就可以开始构建了，而不用等待
  该目标全部构建完成。
- export\_incs: list，指示生成的头文件的搜索路径，类似于`cc_library.export_incs`，不过需要注意这里的是相对于目标目录。
- system\_export\_incs: list，作用与 `export_incs` 相同，但消费者编译时使用 `-isystem` 代替 `-I`。适用于生成的头来自第三方 / vendored 代码、其自身的诊断不应该被消费者的 `-Werror` 升级为错误的场景。典型用户：自定义 `cmake_build` / `autotools_build` 宏。路径语义同 `export_incs`（相对于目标目录）。
- cleans: list，执行 clean 命令时额外要删除的路径列表，可以是文件或目录，相对于 `OUT_DIR`。`clean` 时 `outs` 里的文件总是会被删除，但是如果会生成一些额外的文件或者目录，将其纳入 `cleans` 里可以保证 clean 时也能被删除。
- heavy: bool 这是不是一个‘重’目标，也就是会消耗大量的 CPU 或内存，使得不能和其他任务并行或者并行太多。
  开启本选项会降低构建性能，但是有助于减少资源不足导致的构建失败。

```python
gen_rule(
    name='test_gen_target',
    cmd='echo what_a_nice_day;touch test2.c',
    deps=[':test_gen'],                         # 可以有deps，也可以被别的target依赖
    outs=['test2.c']
)
```

注意：

- `srcs` 可以为空，但是 `outs` 不能为空，且 `cmd` / `cmd_bash` / `cmd_bat` 至少要设一个。
- `gen_rule` 只应该把输出文件生成在相应的结果输出目录下，不应该污染源代码树。但是你在其他目标中引用
  `gen_rule` 生成的源文件时，只需要假设这些文件是生成在源代码目录下，不需要考虑结果目录前缀。
- 命令执行后务必返回正确的退出码，0 表示成功，其他值表示失败。
- 成功的命令不应该输出无关的信息，失败的命令要输出简练而有用的错误信息。
- 命令中需要用到 `$` 时，比如展开环境变量等场景，需要双写为 `$$`，比如 `$$(pwd)`。
- 多个重复或者相似的 `gen_rule`，应该考虑定义为扩展，并在单独的 `.bld` 文件中维护，
  通过 [`load`](extension.md#load-函数) 函数来引入，以减少代码冗余并更好维护。
