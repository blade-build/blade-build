# 构建protobuf 和 thrift #

## proto_library ##

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

当 proto_library 被 Java 目标依赖时，会自动构建 Java 相关的结果，Python也类似。
因此同一个proto_library目标可以被多种语言所使用。

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

如果你想生成C++的其他后缀名代码，可以使用 `cpp_outs` 参数。
默认值是 `['.pb']`。例如，如果你想使用grpc插件生成 `rpc_meta_info.pb.cc/h` 和 `rpc_meta_info.grpc.pb.cc/h`, 那么设置 `cpp_outs = [".pb', '.grpc.pb']`

另外，使用 `plugin_opts` 传递给插件所需参数, 例如 `plugin_opts={"plugin_name":["option1", "option2.."]},`.
Blade 会传递 `--plugin_name_opt=option1 --plugin_name_opt=option2` 给 grpc 插件.

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

## thrift_library ##

用于定义thrift库目标
deps 为import所涉及的其他thrift_library
自动依赖thrift，使用者不需要再显式指定。
构建时自动调用thrift命令生成cpp和h，并且编译成对应的cc_library

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

C++中使用生成的头文件时，规则类似proto，需要带上相对BLADE_ROOT的目录前缀。

* thrift 0.9版（之前版本未测）有个[bug](https://issues.apache.org/jira/browse/THRIFT-1859)，
  需要修正才能使用，此bug已经在开发版本中修正)
