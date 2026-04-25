# 编写 BUILD 文件

Blade 通过一系列名字为 `BUILD`（全大写）的文件来描述构建目标，这些文件需要由开发者编写。每个 `BUILD` 文件通过一组目标描述函数，描述一个目标的源文件、所依赖的其他目标，以及其他一些属性。

## BUILD 文件的示例

构建脚本很简单：

范例：common/base/string/BUILD

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

BUILD 文件是声明式的，只需要列出目标名，源文件名和依赖名（如果有的话）即可，不需要指定任何编译和链接命令。

## BUILD 语言

参见 [BUILD 语言](dsl.md)。

## 风格建议

- 四空格缩进，不要用 tab 字符
- 总是用单引号
- 目标名用小写
- src 里的文件名按字母顺序排列
- deps 里先写本目录内的依赖（:target），后写其他目录内的（//dir:name），分别按字母顺序排列。
- 每行放置一个参数时，最后一个参数也以逗号（`,`）结尾，以减少增删参数时影响的行数
- 不同目标之间空一行，前面可以加注释
- 注释的 `#` 后面空一格，比如 `# This is a comment`

## 通用属性

Blade 用一组 target 函数来定义目标，这些 target 的通用属性有：

### name

字符串，和路径一起成为 target 的唯一标识，也决定了构建的输出命名

### srcs

列表或字符串，构建该对象需要的源文件，一般在当前目录，或相对于当前目录的子目录中。

我们也提供了一个 [glob](functions.md#glob) 函数通过通配符来获取源文件列表。

### deps

列表或字符串，该对象所依赖的其它 targets。

允许的格式：

- "//path/to/dir:name" 其他目录下的 target，path 为从 BLADE_ROOT 出发的路径，name 为被依赖的目标名。看见就知道在哪里。
- ":name" 当前 BUILD 文件内的 target， path 可以省略。
- "#name" 系统库。直接写#跟名字即可，比如#pthread，#z 分别相当于链接命令行上的-lpthread 和-lz，但是会被传递给依赖这个库的其他目标。

### visibility

目标模式的列表或字符串，控制该目标对哪些其他目标可见，特殊值 `PUBLIC` 表示对所有目标可见，同一目录下的目标之间总是相互可见。

例如：

```python
visibility = []                                             # 私有，仅对当前 BUILD 文件可见
visibility = ['PUBLIC']                                     # 对所有目标可见
visibility = ['//module1:program12', '//module1:program2']  # 仅对这两个目标可见
visibility = ['//module2:*']                                # 仅对 module2 目录下的目标可见，但不对其子目录可见
visibility = ['//module3:...']                              # 仅对 module3 及其所有子目录下的目标可见
```

在 Blade 1 中，目标默认都是 `PUBLIC` 的。在 Blade 2 中，为了适应更大规模的项目的依赖管理，调整为默认私有。
对于现存项目中已经存在的目标，可以通过 [`legacy_public_targets`](config.md#global_config) 配置项设置为 `PUBLIC`，仅要求对新增的目标显式设置。

### tags

目标的标签，用户可以设置和查询。Blade 对每种目标设置了一些默认标签。

标签必须由组名和名字两部分构成，以冒号分割。

Blade 对各种构建目标预设了一些标签：

- 按编程语言：`lang:cc`, `lang:java`, `lang:py`, `lang:proto` 等。
- 按类型：`type:binary`, `type:test`, `type:library`
- 其他额外属性：`type:prebuilt`

比如 `cc_library` 目标自动具有 `['lang:cc', 'type:library']` 属性。

默认标签还没有制定详细命名规范，因此将来有可能改变。

标签最大的用途是在命令行查询和过滤，比如只构建某些语言的目标，排除某些类型的目标等。
参见[命令行参考](command_line.md)。

## 构建规则

- [构建 C/C++目标](build_rules/cc.md)
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

- [BUILD 中可以调用的通用函数](functions.md)
- 通过[扩展](build_rules/extension.md)机制创建和使用自定义函数和规则
