# Extension

Although `gen_rule` has allowed us to customize some build rules, it will be more concise
and convenient to define extensions for scenarios that need to be reused.

## Define Extension

Suppose we want to support an awesome file type, first compile it into a C file, and then compile
it into `cc_library`, we can define the build rule in a `awesome_build_rules.bld` file:

```python
def awesome_library(name, srcs=[], deps=[]):
    cc_srcs = [src + '.c' for src in srcs]
    gen_rule(name=name+'_cc', srcs=srcs, outs=cc_srcs, cmd=<...>)
    cc_library(name=name, srcs=cc_srcs, deps=deps)
```

Remember the `gen_rule` is a useful native rule when you create your own rules.

Since the built-in rules can be overridden in the extension, you can enforce using the built-in rules
by adding the `native.` prefix before the rule name.
The `native.` prefix can only be used in extensions but not in `BUILD` files.

```python
def awesome_library(name, srcs=[], deps=[]):
    cc_srcs = [src + '.c' for src in srcs]
    native.gen_rule(name=name+'_cc', srcs=srcs, outs=cc_srcs, cmd=<...>)
    native.cc_library(name=name, srcs=cc_srcs, deps=deps)
```

In addition to functions, you can also define constants:

```python
GTEST_LIBS = ["//thirdparty/gtest:gtest"]
```

### Suggested Style

- Using the `.bld` extension name
- Using the `_` prefix for private symbols

## Use Extension

We support 2 ways to load extensions into `BUILD` file, `load` and `include`.
In both ways, The loaded symbols are only **visible to current `BUILD` file**.

These function supports the path of the subdirectory relative to the current directory and
the path of the relative workspace starting with `//`.

### the `load` function

Load extension and import symbols into current `BUILD` file.

Prototype:

```python
def load(extension_label, *symbols, **aliases):
```

`symbols` are the symbol names to be imported, `aliases` are the symbol names to be imported as aliases.
Symbols beginning with an underscore will not be exported and therefore cannot be imported.

Use:

```python
load('//common/awesome_build_rules.bld', 'awesome_library')

awesome_library(  # Use imported rule
    name='awesome_lib',
    srcs=['my.awesome', 'your.awesome'],
)
```

Globals symbols such as functions and constants can be imported. Symbols beginning with an underscore(`_`) will not be
exported and therefore cannot be imported.

Alias mechanism is used to resolve name conflicts:

```python
load('//common/awesome_build_rules1.bld', my_awesome_library='awesome_library')
load('//common/awesome_build_rules2.bld', your_awesome_library='awesome_library')
```

When the extension is loaded, it has nothing to do with the current context. You can only access the symbols imported
from the extension in the BUILD file, but you cannot access the symbols defined in the current BUILD file in the extension.
No matter how many times the same extension file is loaded in BUILD files, it is actually read and parsed only once.

## The `include` function

The `include` function is like the `#include` directive in C language, it includes the file content into current `BUILD` file.

Use:

```python
include('//common/awesome_build_rules.bld')
...
```

You should use `load` rather than `include` in most case.
