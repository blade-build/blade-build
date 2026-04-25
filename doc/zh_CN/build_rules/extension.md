# 扩展

虽然 `gen_rule` 已经让我们能够自定义一些构建规则，但是对于需要重复使用的场景，定义成扩展会更简洁方便。

## 定义扩展

假设我们要支持一种新的 awesome 文件类型，需要先编译成 C 文件，再编译成 `cc_library`，那么可以定义构建规则扩展文件 `awesome_build_rules.bld`：

```python
def awesome_library(name, srcs=[], deps=[]):
    cc_srcs = [src + '.c' for src in srcs]
    gen_rule(name=name+'_cc', srcs=srcs, outs=cc_srcs, cmd=<...>)
    cc_library(name=name, srcs=cc_srcs, deps=deps)
```

请记住，当你创建自定义规则时，`gen_rule` 是个很有用的内置规则。

由于通过扩展的方式可以覆盖内置规则，你可以用 `native.` 前缀来确保不受影响地使用内置规则。
`native.` 前缀只能用在扩展中而不能用于 `BUILD` 文件中。

```python
def awesome_library(name, srcs=[], deps=[]):
    cc_srcs = [src + '.c' for src in srcs]
    native.gen_rule(name=name+'_cc', srcs=srcs, outs=cc_srcs, cmd=<...>)
    native.cc_library(name=name, srcs=cc_srcs, deps=deps)
```

除了函数外，也可以定义常量：

```python
GTEST_LIBS = ["//thirdparty/gtest:gtest"]
```

### 风格建议

扩展定义文件的扩展名为 `.bld`，不希望被直接使用的私有符号应当以下划线（`_`）开始。

## 使用扩展

Blade 支持 2 种方式使用扩展，分别是 `load` 和 `include`，无论哪种方式，都支持相对当前目录的子目录路径和 `//`
开头的相对 workspace 的路径，并且导入的符号**仅对当前 `BUILD` 文件有效**。

### load 函数

加载扩展，并导入指定名字的符号。

原型：

```python
def load(extension_label, *symbols, **aliases):
```

其中 symbols 为要导入的符号名，aliases 参数则用来支持以别名的方式导入，这两个参数都是可变个数的参数。
下划线开头的符号不会被导出因此也无法被导入。

用法：

```python
load('//common/awesome_build_rules.bld', 'awesome_library')

awesome_library(  # 使用扩展规则
    name='awesome_lib',
    srcs=['my.awesome', 'your.awesome'],
)
```

全局符号，例如函数和常量均可导入。

如果可能存在名字冲突，则可以通过别名机制来解决：

```python
load('//common/awesome_build_rules1.bld', my_awesome_library='awesome_library')
load('//common/awesome_build_rules2.bld', your_awesome_library='awesome_library')
```

扩展被加载时与其所处的上下文无关，只能在 BUILD 文件中访问到从扩展中导入的符号，在扩展里则无法访问到当前 BUILD 文件中定义的符号。
同一个扩展文件不管在多少 BUILD 文件中被加载多少次，实际上都只读取和解析一次。

### include 函数

`include` 函数则类似 C 语言中的 `#include` 指令，相当于把被包含文件中的内容原样展开在当前包含它的 BUILD 文件中。

```python
include('//common/awesome_build_rules.bld')
...
```

由于 `load` 更清晰安全可靠，绝大多数情况下，我们建议优先使用 `load` 而不是 `include`。
