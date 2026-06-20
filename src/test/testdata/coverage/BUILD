# Self-contained fixture for the C/C++ coverage report test (#643):
# a library + a cc_test with its own main (no gtest, no prebuilt deps).
cc_library(name = 'cov_lib', srcs = 'cov_lib.cc', hdrs = 'cov_lib.h')
cc_test(name = 'cov_lib_test', srcs = 'cov_lib_test.cc', deps = [':cov_lib'])
