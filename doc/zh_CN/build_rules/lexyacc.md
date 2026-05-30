# 构建 lex 和 yacc

## lex_yacc_library

用于定义 lex/yacc 目标，生成编译器所需的词法分析器与语法分析器。
由于二者通常搭配使用，并且编译 lex 时，通常采用 yacc 生成的 yy.tab.h 来定义，而编译 yacc 生成的 yy.tab.cc 时，又会调用 lex 生成的 parse 函数，整体上形成相互依赖。
因此我们把二者合并为一条规则。srcs 必须为二元列表，后缀分别为 ll 和 yy。

本规则构建时按依赖关系自动调用 flex 和 bison，并且编译成对应的 cc_library，生成正确的头文件。

属性：

- `recursive=True` — 生成可重入的 C scanner。
- `prefix='xxx'` — 修改 `yy` 符号前缀（传给 flex `-P` / bison `-p`），让多个
  parser 可在同一个二进制中共存，避免 `yyparse` / `yylval` 等全局符号冲突。
- `lexflags=[...]` / `yaccflags=[...]` — 直接透传给 flex / bison 的额外参数。
  注意：改变生成文件名的参数不受支持——blade 按自己的规则推算这些文件名，不会感知到此类覆盖。

也支持大部分 [cc_library 的属性](cc.md#cc_library)。

示例：

```python
lex_yacc_library(
     name = 'parser',
     srcs = [
         'line_parser.ll',
         'line_parser.yy'
     ],
     deps = [
         ":xcubetools",
     ],
     recursive = True
)
```

### 生成的头文件

`bison -d` 生成的头文件以 yacc 源文件命名：C++ 语法（`.yy`）为 `<yacc 文件>.hh`，
C 语法（`.y`）为 `<yacc 文件>.h`。上例即 `line_parser.yy.hh`，其中声明了 token
和 `yyparse`。

使用该 parser 的目标按工作区相对路径 `#include` 它，与引用其它生成头文件一样：

```c++
#include "path/to/line_parser.yy.hh"
```

include 这个头文件也是头文件依赖检查识别"你的目标确实用到了该 `lex_yacc_library`"
的依据；如果只靠自己的前向声明使用其中的符号而不 include 此头文件，这条依赖会被
判定为未使用。
