"""Regression test for issue #1169.

The `cxxhdrs` rule preprocesses each public header to produce an inclusion-stack
(`.incstk`) file used by the missing-deps / unused-deps checks. If the command
omits `-H`, the wrapper's awk has nothing to extract and the file ends up empty
-- which silently breaks the checks for header-only libraries (every dep used
only through a header looks unused).

This test builds a header-only library whose header `#include`s a dep, and
asserts that the resulting `.incstk` is non-empty and records the include.
"""

import os

import blade_test


class TestHeaderOnlyIncstk(blade_test.TargetTest):
    def setUp(self):
        self.doSetUp('header_only_incstk', target='hdr_only')

    def testIncstkRecordsDirectInclude(self):
        self.assertTrue(self.runBlade('build'))
        incstk = 'build_release/header_only_incstk/hdr_only.objs/hdr_only.h.incstk'
        self.assertTrue(os.path.exists(incstk), '%s was not generated' % incstk)
        self.assertGreater(
            os.path.getsize(incstk), 0,
            "header inclusion stack is empty -- the cxxhdrs preprocess must pass "
            "-H so the wrapper can extract the stack (issue #1169)")
        with open(incstk) as f:
            content = f.read()
        self.assertIn(
            'header_only_incstk/inner.h', content,
            'expected inner.h to be recorded as a direct include of hdr_only.h')


if __name__ == '__main__':
    blade_test.run(TestHeaderOnlyIncstk)
