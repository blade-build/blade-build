# 编写 BUILD 文件

Blade 通过一组名为 `BUILD`（全大写）的文件来描述构建目标。每个 `BUILD` 文件以声明式语法，通过一组目标描述函数，指定一个或多个目标的源文件、依赖关系与配置属性。

## BUILD 文件示例

示例：`common/base/string/BUILD`

```python
cc_library(
    name = 'string',
    srcs = [
        'algorithm.cpp',
        'format.cpp',
        'concat.cpp',
    ],
    hdrs = [
        'algorithm.h',
        'format.h',
        'concat.h',
    ],
    deps = ['//common/base:int'],
)
```

BUILD 文件采用声明式语法：开发者只需声明目标名、源文件与依赖，而无需显式描述编译或链接命令。

## BUILD 语言

参见 [BUILD 语言](dsl.md)。

## 风格建议

- 四空格缩进，不要使用 tab 字符
- 统一使用单引号（`'`），而非双引号（`"`）
- 目标名全部小写
- `srcs` 中的文件名按字母顺序排列
- `deps` 中先列本目录内的依赖（`:target`），再列其他目录下的依赖（`//dir:name`），各自按字母顺序排列
- 每行一个参数时，最后一个参数也以逗号（`,`）结尾，以减少增删参数时的行变更数
- 不同目标之间留一个空行，必要时在目标前加注释
- 注释的 `#` 后面保留一个空格，例如 `# This is a comment`

## 通用属性

Blade 通过一组 target 函数来定义构建目标，这些目标共有的通用属性如下：

### name

字符串。与目录路径一起构成目标的唯一标识，同时决定构建产物的输出名。

### srcs

列表或字符串。构建该目标所需的源文件，通常位于当前目录或其子目录中。

Blade 还提供了 [`glob`](functions.md#glob) 函数，用于通过通配符生成源文件列表。

### deps

列表或字符串。声明该目标所依赖的其他目标。

允许的格式：

- `'//path/to/dir:name'`：其他目录下的目标。`path` 为从 `BLADE_ROOT` 出发的路径，`name` 为目标名，一目了然地指出依赖位置。
- `':name'`：当前 BUILD 文件内的目标，路径可以省略。
- `'#name'`：系统库。直接写 `#` 加名字即可，例如 `#pthread`、`#z` 分别等价于链接命令行上的 `-lpthread` 和 `-lz`；同时会被传递给依赖该库的其他目标。

### visibility

目标模式的列表或字符串，用于控制该目标对哪些目标可见。特殊值 `PUBLIC` 表示对所有目标可见；同一目录下的目标之间始终相互可见。

示例：

```python
visibility = []                                             # 私有，仅对当前 BUILD 文件可见
visibility = ['PUBLIC']                                     # 对所有目标可见
visibility = ['//module1:program12', '//module1:program2']  # 仅对这两个目标可见
visibility = ['//module2:*']                                # 仅对 module2 目录下的目标可见，不含其子目录
visibility = ['//module3:...']                              # 对 module3 及其所有子目录下的目标均可见
```

在 Blade 1 中，所有目标默认都是 `PUBLIC`。在 Blade 2 中，为了适应更大规模项目的依赖管理，默认改为私有。
对于既有项目中的存量目标，可以通过 [`legacy_public_targets`](config.md#global_config) 配置项整体设为 `PUBLIC`，只在新增目标上显式声明可见性即可。

### tags

目标的标签，用户可以自行设置和查询。Blade 会为每种目标预置一些默认标签。

标签由「组名」和「名字」两部分组成，中间以冒号分隔。

Blade 为各类构建目标预设了一些标签：

- 按编程语言：`lang:cc`、`lang:java`、`lang:py`、`lang:proto` 等
- 按类型：`type:binary`、`type:test`、`type:library`
- 其他属性：`type:prebuilt`

例如 `cc_library` 目标会自动具有 `['lang:cc', 'type:library']` 标签。

目前默认标签尚未形成严格的命名规范，未来可能会调整。

标签最大的用途是在命令行中查询与过滤，例如只构建某几种语言的目标、排除某类目标等。
详见[命令行参考](command_line.md)。

## 构建规则

- [构建 C/C++ 目标](build_rules/cc.md)
- [构建 protobuf 和 thrift](build_rules/idl.md)
- [构建 Java](build_rules/java.md)
- [构建 Scala](build_rules/scala.md)
- [构建 Python](build_rules/python.md)
- [构建 Lex 和 Yacc](build_rules/lexyacc.md)
- [构建 SWIG](build_rules/swig.md)
- [Bash 测试](build_rules/shell.md)
- [自定义规则构建](build_rules/gen_rule.md)
- [文件打包](build_rules/package.md)

## 其他特性

- BUILD 文件中可调用的[通用函数](functions.md)
- 通过[扩展机制](build_rules/extension.md)创建和使用自定义函数与规则
