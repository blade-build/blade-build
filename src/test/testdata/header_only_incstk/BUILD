cc_library(
    name = 'inner',
    hdrs = 'inner.h',
    visibility = 'PUBLIC',
)

cc_library(
    name = 'hdr_only',
    hdrs = 'hdr_only.h',
    deps = [':inner'],
    visibility = 'PUBLIC',
)
