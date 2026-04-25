# 命令行参考

## 基本命令行语法

```bash
blade <subcommand> [options]... [target patterns]...
```

## 子命令

Blade 支持以下子命令：

- `build` —— 构建指定目标
- `test` —— 构建并执行测试
- `clean` —— 清理指定目标
- `dump` —— 导出有用的信息
- `query` —— 查询目标依赖关系
- `run` —— 构建并执行单个可执行目标

## 目标模式语法

目标模式（target pattern）是以空格分隔的一组模式表达式，用于指定构建目标。它在命令行、配置项以及目标属性中均可使用。

### 支持的模式格式

- `path:name` —— 指定路径下的具体目标
- `path:*` —— 指定路径下的所有目标
- `path` —— 等价于 `path:*`
- `path/...` —— 递归匹配指定路径及其所有子目录下的全部目标
- `:name` —— 当前目录下的目标

### 路径解析规则

- **绝对路径：** 以 `//` 开头的路径从工作空间根目录解析
- **直接目标：** 名字部分不含通配符的模式视为直接目标
- **默认行为：** 未指定目标时，Blade 构建当前目录下的所有目标（不包含子目录）
- **空展开：** `...` 作为路径终结符时，即便展开结果为空也不会报错，只要路径存在即可

### 目录搜索行为

- **递归搜索：** Blade 会对 `...` 模式递归搜索 `BUILD` 文件
- **排除机制：** 在目录中放置空的 `.bladeskip` 文件即可将其排除
- **shell 兼容性：** 安装 [ohmyzsh](https://ohmyz.sh/) 后，裸写 `...` 会被展开为 `..\..`，此时请使用 `./...`

## 基于标签的目标过滤

Blade 支持通过 `--tags-filter` 选项基于标签表达式过滤构建目标。每个目标都支持 [tags 属性](build_file.md#tags)。

### 过滤表达式语法

- **标签名：** 使用完整标签名，如 `lang:cc`、`type:test`
- **逻辑运算符：** `not`、`and`、`or`
- **组选择：** `group:name1,name2` 用于选择同组的多个标签，等价于 `(group:name1 or group:name2)`
- **复合表达式：** 含空格的表达式请使用引号包裹

### 过滤示例

- `--tags-filter='lang:cc'` —— 仅保留 `cc_*` 目标
- `--tags-filter='lang:cc,java'` —— 保留 `cc_*` 与 `java_*` 目标
- `--tags-filter='lang:cc and type:test'` —— 仅保留 `cc_test` 目标
- `--tags-filter='lang:cc and not type:test'` —— 保留 `cc_*` 目标但排除 `cc_test`

### 过滤作用范围

标签过滤只对通过通配符展开的目标生效；直接目标及其依赖不会被过滤。任何被未过滤目标所依赖的目标都会保留在构建列表中，无论其标签是否匹配。

### 查询可用标签

查询当前可用的标签列表：

```console
$ blade dump --all-tags ...
[
   "lang:cc",
   "lang:java",
   "lang:lexyacc",
   "lang:proto",
   "lang:py",
   "type:binary",
   "type:foreign",
   "type:gen_rule",
   "type:library",
   "type:maven",
   "type:prebuilt",
   "type:system",
   "type:test",
   "xxx:xxx"
]
```

## 子命令选项

不同子命令支持不同选项，运行 `blade <subcommand> --help` 可查看完整选项列表。

### 常用命令行选项

- `-m32`、`-m64` —— 目标架构（32 位 / 64 位），默认自动探测
- `-p PROFILE` —— 构建模式（`debug` / `release`），默认为 `release`
- `-k`、`--keep-going` —— 遇到非致命错误时继续执行
- `-j N`、`--jobs=N` —— 并行构建任务数（默认自动并行）
- `-t N`、`--test-jobs=N` —— 并行测试任务数，适用于多 CPU 机器
- `--verbose` —— 显示每条命令的完整命令行
- `-h`、`--help` —— 显示帮助信息
- `--color=yes/no/auto` —— 启用或禁用彩色输出
- `--exclude-targets` —— 加载阶段排除的目标模式（逗号分隔）
- `--generate-dynamic` —— 强制生成动态库
- `--generate-java` —— 为 `proto_library` 和 `swig_library` 生成 Java 文件
- `--generate-php` —— 为 `proto_library` 和 `swig_library` 生成 PHP 文件
- `--generate-go` —— 为 `proto_library` 生成 Go 文件
- `--gprof` —— 启用 GNU gprof 性能分析
- `--coverage` —— 生成代码覆盖率报告（支持 GNU gcov 与 Java jacoco）

## 使用示例

```bash
# 构建当前目录下的所有目标（不包含子目录）
blade build

# 构建当前目录及其所有子目录下的目标
blade build ...

# 构建当前目录下名为 'urllib' 的特定目标
blade build :urllib

# 构建 'app' 目录下的所有目标，但排除 'sub' 子目录
blade build app... --exclude-targets=app/sub...

# 从工作空间根目录和 common 子目录构建并测试所有目标
blade test //common/...
blade test base/...

# 构建并运行 base 子目录下的特定测试目标
blade test base:string_test
```

## 命令行补全

Blade 在安装后自带基础的命令行补全能力。如需更强大的补全功能，请安装 [argcomplete](https://pypi.org/project/argcomplete/)。

### 安装

```console
pip install argcomplete
```

对于非 root 用户，可加 `--user`：

```console
pip install --user argcomplete
```

### 配置

在 `~/.bashrc` 中加入以下一行：

```bash
eval "$(register-python-argcomplete blade)"
```
