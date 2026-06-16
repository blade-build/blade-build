# 构建 protobuf 和 thrift

## proto_library

用于定义 protobuf 目标
deps 为 import 所涉及的其他 proto_library
自动依赖 protobuf 运行库，使用者不需要再显式指定。

示例：

```python
proto_library(
    name = 'rpc_meta_info_proto',
    srcs = 'rpc_meta_info.proto',
    deps = ':rpc_option_proto',
)
```

protobuf_library 支持生成多种语言的目标。

当编译为 C++ 目标时，构建时自动调用 protoc 生成 pb.cc 和 pb.h，并且编译成对应的 C++ 库。

要引用某 proto 文件生成的头文件，需要从 BLADE_ROOT 的目录开始，只是把 proto 扩展名改为 pb.h 扩展名。
比如 //common/base/string_test.proto 生成的头文件，路径为 "common/base/string_test.pb.h"。

当 proto_library 被 Java 目标依赖时，会自动构建 Java 相关的结果，Python 也类似。
因此同一个 proto_library 目标可以被多种语言所使用。

如果需要强制生成某种语言的目标库，可以通过 `target_languages` 参数来指定：

```python
proto_library(
    name = 'rpc_meta_info_proto',
    srcs = 'rpc_meta_info.proto',
    deps = ':rpc_option_proto',
    target_languages = ['java', 'python'],
)
```

C++ 代码总是会生成。

如果你想生成 C++的其他后缀名代码，可以使用 `cpp_outs` 参数。
默认值是 `['.pb']`。例如，如果你想使用 grpc 插件生成 `rpc_meta_info.pb.cc/h` 和 `rpc_meta_info.grpc.pb.cc/h`，那么设置 `cpp_outs = ['.pb', '.grpc.pb']`。

另外，使用 `plugin_opts` 传递插件所需参数，例如 `plugin_opts = {"plugin_name": ["option1", "option2"]}`。
Blade 会传递 `--plugin_name_opt=option1 --plugin_name_opt=option2` 给 grpc 插件。

```python
proto_library(
    name = 'rpc_meta_info_proto',
    srcs = 'rpc_meta_info.proto',
    deps = ':rpc_option_proto',
    target_languages = ['java', 'python'],
    plugins = ['grpc'],
    cpp_outs = ['.pb', '.grpc.pb'],
    plugin_opts = {
        'grpc': ["option1", "option2"],
    },
)
```

### 导入根目录：`strip_import_prefix`

默认情况下，proto 的 import 路径和生成头文件的引用路径都相对于 workspace 根目录：
位于 `//foo/bar/x.proto` 的 proto 以 `import "foo/bar/x.proto";` 导入，并生成
`"foo/bar/x.pb.h"`。

有些工程会把 proto 根置于某个源码子目录下：它们的 proto 之间以
`import "bar/x.proto";` 互相导入，C++ 代码以 `#include "bar/x.pb.h"` 引用，而
`bar/` 实际位于例如 `src/` 之下。此时把 `strip_import_prefix` 设为该根目录
（相对于 BUILD 所在包的路径），Blade 就会用 `--proto_path=<包>/<前缀>` 编译，
使 import 和生成的 `#include` 都相对该根目录解析，而非 workspace 根：

```python
proto_library(
    name = 'options_proto',
    srcs = 'src/foo/bar/x.proto',   # import "bar/y.proto"，代码 #include "bar/x.pb.h"
    strip_import_prefix = 'src/foo', # -> 以 --proto_path=src/foo 编译
)
```

这是 Bazel `proto_library(strip_import_prefix=...)` 的对应物，目前作用于生成的
C++ 产物。

## thrift_library

用于定义 thrift 库目标
deps 为 import 所涉及的其他 thrift_library
自动依赖 thrift，使用者不需要再显式指定。
构建时自动调用 thrift 命令生成 cpp 和 h，并且编译成对应的 cc_library

```python
thrift_library(
    name = 'shared_thrift',
    srcs = 'shared.thrift',
)

thrift_library(
    name = 'tutorial_thrift',
    srcs = 'tutorial.thrift',
    deps = ':shared_thrift'
)
```

C++中使用生成的头文件时，规则类似 proto，需要带上相对 BLADE_ROOT 的目录前缀。

* thrift 0.9 版（之前版本未测）有个 [bug](https://issues.apache.org/jira/browse/THRIFT-1859)，
  需要修正才能使用，此 bug 已经在开发版本中修正。
