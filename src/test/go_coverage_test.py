# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration test for `blade test --coverage` Go coverage (#672).

Stands up a throwaway Go module workspace, builds a go_test under
--coverage (so the test binary is `-cover` instrumented and run with
-test.coverprofile), and asserts the merged `go tool cover` HTML report.
Skipped when the go toolchain is unavailable.
"""


import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest


@unittest.skipUnless(shutil.which('go'), 'go toolchain not available')
class TestGoCoverage(unittest.TestCase):
    """`blade test --coverage` produces a Go coverage report."""

    def setUp(self):
        self.cur_dir = os.getcwd()
        here = os.path.dirname(os.path.abspath(__file__))
        self.blade = os.path.join(here, '..', '..', 'blade')
        self.work = tempfile.mkdtemp(prefix='blade_go_cov_')

    def tearDown(self):
        os.chdir(self.cur_dir)
        shutil.rmtree(self.work, ignore_errors=True)

    def _write(self, rel, text):
        path = os.path.join(self.work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def testGoCoverageReport(self):
        go = shutil.which('go')
        self._write('BLADE_ROOT',
                    "go_config(go='%s', go_home='%s')\n"
                    % (go, os.path.join(self.work, 'gopath')))
        self._write('go.mod', 'module calc\n\ngo 1.20\n')
        self._write('calc/calc.go', textwrap.dedent('''\
            package calc
            func Add(a, b int) int { return a + b }
            func Sub(a, b int) int { return a - b }
            '''))
        self._write('calc/calc_test.go', textwrap.dedent('''\
            package calc
            import "testing"
            func TestAdd(t *testing.T) { if Add(1, 2) != 3 { t.Fatal("bad") } }
            '''))
        self._write('calc/BUILD', textwrap.dedent('''\
            go_library(name='calc', srcs=['calc.go'])
            go_test(name='calc_test', srcs=['calc_test.go'], deps=[':calc'])
            '''))

        os.chdir(self.work)
        p = subprocess.run(
            [self.blade, 'test', 'calc:calc_test', '--coverage'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
        self.assertEqual(p.returncode, 0,
                         'blade test --coverage (go) failed:\n%s' % p.stdout)
        report = os.path.join('build_release_coverage',
                              'go_coverage_report', 'index.html')
        self.assertTrue(os.path.exists(report),
                        'no Go coverage report at %s\n%s' % (report, p.stdout))


if __name__ == '__main__':
    unittest.main()
