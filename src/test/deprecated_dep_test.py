# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration test: depending on a deprecated library warns (#667).

`deprecated` is supported by every library type (not just cc), and a
target depending on a deprecated library is warned regardless of its own
type. Here a py_library marked deprecated is depended on by another
py_library, which must produce the deprecation warning.
"""


import blade_test


class TestDeprecatedDep(blade_test.TargetTest):
    """A target depending on a deprecated library is warned."""

    def setUp(self):
        """setup method."""
        self.doSetUp('deprecated', 'user')

    def testDeprecatedDepWarning(self):
        self.assertTrue(self.runBlade())
        needle = '//deprecated:old is deprecated'
        warned = any(needle in line for line in self.build_output) or \
            any(needle in line for line in self.build_error)
        self.assertTrue(
            warned,
            'expected a deprecation warning for //deprecated:old\n'
            'stdout:\n%s\nstderr:\n%s' % (
                ''.join(self.build_output), ''.join(self.build_error)))


if __name__ == '__main__':
    blade_test.run(TestDeprecatedDep)
