# Build Protobuf and Thrift

## proto_library

Build protobuf targets

```python
proto_library(
    name = 'rpc_meta_info_proto',
    srcs = 'rpc_meta_info.proto',
    deps = ':rpc_option_proto',
)
```

`deps` are other proto_library which are imported.
protobuf runtime library will be depended automatically, needn't to be specified explicitly.

proto_library support generate targets for multiple target languages.

When generate for C++ code, it generate a c++ library with corresponding header files.
To include the generated header file of a proto file, you should include it with the full path from
the root of the workspace, replace the `proto` suffix into `pb.h`.
For example, the header file of `//common/base/string_test.proto` is "common/base/string_test.pb.h".

When a java targets depends on a proto_library, the java relatived code will be generated automatically,
it is also similar to other target languages,such as python. so we only need one proto_library for
multiple target languages.

If you want to generate code for specified languages unconditionly, you can use the `target_languages` argument:

```python
proto_library(
    name = 'rpc_meta_info_proto',
    srcs = 'rpc_meta_info.proto',
    deps = ':rpc_option_proto',
    target_languages = ['java', 'python'],
)
```

The `cpp` target code is always generated.

If you want to generate some cpp code with other suffix names, you can use `cpp_outs` attributes.
The default value is `['.pb']`. For example, if you want to use grpc plugin to generate `rpc_meta_info.pb.cc/h` and `rpc_meta_info.grpc.pb.cc/h`, set `cpp_outs = [".pb', '.grpc.pb']`

Besides, use `plugin_opts` to pass some options to plugins, like `plugin_opts={"plugin_name":["option1", "option2.."]},`.
Blade will pass `--plugin_name_opt=option1 --plugin_name_opt=option2` to grpc plugin.

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

### Import root: `strip_import_prefix`

By default a proto is imported and its generated header is referenced relative
to the workspace root: a proto at `//foo/bar/x.proto` is imported as
`import "foo/bar/x.proto";` and generates `"foo/bar/x.pb.h"`.

Some projects instead root their protos at a source subdirectory — their protos
`import "bar/x.proto";` and their C++ `#include "bar/x.pb.h"`, where `bar/` lives
under e.g. `src/`. Set `strip_import_prefix` to that root (a path relative to
the BUILD package) so Blade compiles with `--proto_path=<package>/<prefix>` and
both the `import`s and the generated `#include`s resolve there instead of at the
workspace root:

```python
proto_library(
    name = 'options_proto',
    srcs = 'src/foo/bar/x.proto',   # imports "bar/y.proto"; code #includes "bar/x.pb.h"
    strip_import_prefix = 'src/foo', # -> proto compiles with --proto_path=src/foo
)
```

This is the analog of Bazel's `proto_library(strip_import_prefix=...)`. It
currently affects the generated C++ outputs.

## thrift_library

Can be used to generate thrift C++ library
deps is the other thrift_library which are imported.
thrift runtime will be depended automatically, needn't to be specified explicitly.
The generated result is a c++ linrary with with corresponding header files.

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

Similay to proto_library, to include generated header files, the full path is also required.
