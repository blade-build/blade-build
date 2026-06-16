proto_library(
    name = 'rpc_option_proto',
    srcs = 'rpc_option.proto',
    visibility = ['PUBLIC'],
)

proto_library(
    name = 'rpc_meta_info_proto',
    srcs = 'rpc_meta_info.proto',
    deps = ':rpc_option_proto',
    visibility = ['PUBLIC'],
)

cc_library(
    name='use_protos',
    srcs=['use_protos.cpp'],
    hdrs=[],
    deps=[
         ':rpc_meta_info_proto',
         ':rpc_option_proto'
    ],
    visibility = ['PUBLIC'],
)

# Two proto_libraries rooted under different strip_import_prefix-es: the
# dependent must compile with the dependency's import root added as a `-I`
# proto-path so a cross-root `import` resolves.
proto_library(
    name = 'other_root_proto',
    srcs = 'sub/pkg/other.proto',
    strip_import_prefix = 'sub',          # -> _import_root proto/sub
    visibility = ['PUBLIC'],
)

proto_library(
    name = 'cross_root_proto',
    srcs = 'main_root/a.proto',
    strip_import_prefix = 'main_root',    # -> _import_root proto/main_root
    deps = ':other_root_proto',
    visibility = ['PUBLIC'],
)
