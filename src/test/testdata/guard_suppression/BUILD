cc_library(
    name = 'foo',
    hdrs = 'foo.h',
    visibility = 'PUBLIC',
)

cc_library(
    name = 'bar',
    hdrs = 'bar.h',
    deps = [':foo'],
    visibility = 'PUBLIC',
)

cc_library(
    name = 'qux',
    srcs = 'qux.cc',
    hdrs = [],
    deps = [':foo', ':bar'],
    visibility = 'PUBLIC',
)
