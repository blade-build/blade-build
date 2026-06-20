"""Regression test for issue #1171.

When a header has a multiple-include guard AND is reached transitively before
its direct `#include`, GCC's guard optimization suppresses the second read and
`-H` emits no depth-1 line for it. Without the source-scan supplement,
`direct_hdrs` (the depth-1 set the checks consume) misses that direct include,
which produces a loud false positive on the unused-deps check and silent
false negatives on missing-deps / private-header / undeclared-header checks.

This test exercises the real ccincchk pipeline on a target where qux.cc
first `#include`s bar.h (which transitively pulls foo.h) and then directly
`#include`s foo.h. The post-check `direct_hdrs` recorded in the .details file
must contain BOTH foo.h and bar.h. Without the fix, foo.h would be absent.
"""

import os
import pickle

import blade_test


class TestGuardSuppression(blade_test.TargetTest):
    def setUp(self):
        self.doSetUp('guard_suppression', target='qux')

    def testDirectHdrsIncludeGuardSuppressedInclude(self):
        self.assertTrue(self.runBlade('build'))
        details_path = 'build_release/guard_suppression/qux.incchk.details'
        self.assertTrue(os.path.exists(details_path),
                        '%s not produced by ccincchk' % details_path)
        with open(details_path, 'rb') as f:
            details = pickle.load(f)
        direct_hdrs = details.get('direct_hdrs', set())
        # bar.h is the first #include -> always shows up at depth-1 in -H.
        self.assertIn('guard_suppression/bar.h', direct_hdrs,
                      'bar.h should be in depth-1 direct includes')
        # foo.h is `#include`d directly by qux.cc but transitively pulled in
        # first via bar.h, so its second read is guard-suppressed and emits no
        # depth-1 line. The source-scan supplement (#1171) must add it back.
        self.assertIn('guard_suppression/foo.h', direct_hdrs,
                      'foo.h should be supplemented from the source scan even '
                      'though guard suppression elided its depth-1 -H entry')
        # System header mis-quoted as `#include "stdio.h"`: source-scan picks
        # it up, but the wrapper's awk strips absolute paths from the .incstk
        # and the supplement is intersected with compiled paths, so it must
        # NOT land in direct_hdrs (where it would trigger a false-positive
        # "undeclared header" warning).
        self.assertNotIn('stdio.h', direct_hdrs,
                         'system header spelled with quotes must be filtered '
                         'out by the intersection with compiled paths')
        # `#if 0 / #include "ghost.h" / #endif`: ghost.h does not exist; the
        # compiler never opens it, so it is not in the .incstk and the
        # intersection drops it. This is the contract that the scanner stays
        # naive and the .incstk is the source of truth for what was used.
        self.assertNotIn('guard_suppression/ghost.h', direct_hdrs,
                         'header inside #if 0 must not be in direct_hdrs '
                         '(intersection with compiled paths filters it)')


if __name__ == '__main__':
    blade_test.run(TestGuardSuppression)
