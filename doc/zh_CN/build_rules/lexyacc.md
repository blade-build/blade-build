# 构建 lex 和 yacc

## lex_yacc_library

用于定义 lex/yacc 目标，生成编译器所需的词法分析器与语法分析器。
由于二者通常搭配使用，并且编译 lex 时，通常采用 yacc 生成的 yy.tab.h 来定义，而编译 yacc 生成的 yy.tab.cc 时，又会调用 lex 生成的 parse 函数，整体上形成相互依赖。
因此我们把二者合并为一条规则。srcs 必须为二元列表，后缀分别为 ll 和 yy。

本规则构建时按依赖关系自动调用 flex 和 bison，并且编译成对应的 cc_library，生成正确的头文件。

属性：

- recursive=True 生成可重入的 C scanner。

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
