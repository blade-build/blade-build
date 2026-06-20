# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration test for `blade test --coverage` C/C++ coverage (#643).

A `--coverage` test build goes to its own sibling build dir
(`build64_release_coverage`), instruments the cc targets, and -- when gcovr
is available -- produces an HTML report. The plain `build64_release` name is
left untouched.
"""


import os
import shutil

import blade_test


class TestCcCoverage(blade_test.TargetTest):
    """`blade test --coverage` instruments cc targets and reports."""

    COVERAGE_BUILD_DIR = 'build64_release_coverage'

    def setUp(self):
        """setup method."""
        self.doSetUp('coverage', 'cov_lib_test')
        shutil.rmtree(self.COVERAGE_BUILD_DIR, ignore_errors=True)

    def doTearDown(self):
        # The base harness only cleans build64_release; remove the coverage
        # sibling dir too.
        shutil.rmtree(self.COVERAGE_BUILD_DIR, ignore_errors=True)

    def testCoverageBuildAndReport(self):
        self.assertTrue(self.runBlade('test', '--coverage'),
                        'blade test --coverage failed')
        cov_dir = self.COVERAGE_BUILD_DIR
        # The coverage variant gets its own dir; the plain name is not renamed.
        self.assertTrue(os.path.isdir(cov_dir),
                        'coverage build dir %s not created' % cov_dir)
        # Instrumented and executed -> .gcda data was produced.
        gcda = [f for _d, _s, fs in os.walk(cov_dir) for f in fs
                if f.endswith('.gcda')]
        self.assertTrue(gcda, 'no .gcda coverage data produced under %s' % cov_dir)
        # The HTML report needs gcovr; assert it whenever gcovr is installed.
        if shutil.which('gcovr'):
            report = os.path.join(cov_dir, 'cc_coverage_report', 'index.html')
            self.assertTrue(os.path.exists(report),
                            'gcovr present but no report at %s' % report)


if __name__ == '__main__':
    blade_test.run(TestCcCoverage)
