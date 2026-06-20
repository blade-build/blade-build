# Fixtures for the sanitizer integration tests (#1038): bugs caught only under
# the respective sanitizer.
cc_test(name = 'oob_test', srcs = ['oob_test.cc'])  # heap-buffer-overflow (ASan)
cc_test(name = 'ub_test', srcs = ['ub_test.cc'])    # signed overflow (UBSan)
cc_test(name = 'race_test', srcs = ['race_test.cc'], deps = ['#pthread'])  # data race (TSan)
