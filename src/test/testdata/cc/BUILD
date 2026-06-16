cc_library(
    name = 'prebuilt',
    hdrs = 'prebuilt.h',
    prebuilt = True,
)

cc_library(
    name='lowercase',
    srcs=['plowercase.cpp'],
    hdrs=['plowercase.h'],
    deps=[
        ':prebuilt',
        '#pthread',
        ':static_resource',
    ],
    warning='yes',
    defs=['LOWER_DEF'],
    incs=['include'],
    optimize=['-O3'],
    always_optimize=True,
    link_all_symbols=1,
    visibility = ['PUBLIC'],
)


cc_library(
    name='uppercase',
    srcs=['puppercase.cpp'],
    hdrs=['puppercase.h'],
    deps=['#dl'],
    link_all_symbols=1
)

cc_library(
    name='textual',
    srcs=['textual_user.cpp'],
    hdrs=[],
    # numbers_data.cc is #included textually by textual_user.cpp; it is not a
    # standalone TU and has a non-header extension, so it belongs in
    # textual_hdrs rather than hdrs.
    textual_hdrs=['numbers_data.cc'],
)

resource_library(
    name = 'static_resource',
    srcs = [
        'forms.js',
        'poppy.html'
    ]
)

cc_library(
    name='blade_string',
    srcs=['blade_string.cpp'],
    hdrs=['blade_string.h'],
    warning = 'no',
    deps=[
        ':lowercase',
        ':uppercase',
        '#pthread',
        '#dl'
    ],
    defs=['BLADE_STR_DEF']
)

cc_test(
    name='string_test_main',
    srcs=[
         'string_test.cpp'
         ],
    deps=[
         ':lowercase',
         ':uppercase',
         '#pthread',
         '#dl'
         ],
    warning='yes',
    defs=['BLADE_STR_DEF'],
#dynamic_link=1
)

cc_binary(
    name='string_main_prog',
    srcs=['string_main.cpp'],
    deps=[
        ':lowercase',
        ':uppercase',
        '#pthread',
        '#dl'
    ],
    warning='yes',
    defs=['BLADE_STR_DEF'],
    #dynamic_link=1
)

cc_plugin(
    name='string_plugin',
    srcs=['string_plugin.cpp'],
    deps=[
        ':lowercase',
        ':uppercase',
    ],
    defs=['BLADE_STR_DEF'],
    extra_linkflags='-Wl,-Bsymbolic'
)

