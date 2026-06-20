# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration test for `blade test --coverage` Python coverage (#642).

Stands up a throwaway Python workspace, runs a py_test under --coverage (so
its wrapper executes through `coverage run -p`), and asserts the combined
`coverage html` report. Skipped when coverage.py is unavailable.

The blade subprocess is pointed at this test's own interpreter
(BLADE_PYTHON_INTERPRETER=sys.executable) so the py_test runs under a plain
python that has coverage.py -- not the CI's multi-word self-coverage wrapper.
"""


import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


def _has_coverage():
    return subprocess.call([sys.executable, '-m', 'coverage', '--version'],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL) == 0


@unittest.skipUnless(_has_coverage(), 'coverage.py not available')
class TestPyCoverage(unittest.TestCase):
    """`blade test --coverage` produces a Python coverage report."""

    def setUp(self):
        self.cur_dir = os.getcwd()
        here = os.path.dirname(os.path.abspath(__file__))
        self.blade = os.path.join(here, '..', '..', 'blade')
        self.work = tempfile.mkdtemp(prefix='blade_py_cov_')

    def tearDown(self):
        os.chdir(self.cur_dir)
        shutil.rmtree(self.work, ignore_errors=True)

    def _write(self, rel, text):
        path = os.path.join(self.work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def testPyCoverageReport(self):
        self._write('BLADE_ROOT', '')
        self._write('calc/calc.py', textwrap.dedent('''\
            def add(a, b):
                return a + b
            def sub(a, b):
                return a - b
            '''))
        self._write('calc/calc_test.py', textwrap.dedent('''\
            import unittest
            from calc.calc import add
            class T(unittest.TestCase):
                def test_add(self):
                    self.assertEqual(add(1, 2), 3)
            if __name__ == '__main__':
                unittest.main()
            '''))
        self._write('calc/BUILD', textwrap.dedent('''\
            py_library(name='calc', srcs=['calc.py'])
            py_test(name='calc_test', srcs=['calc_test.py'],
                    main='calc_test.py', deps=[':calc'])
            '''))

        env = os.environ.copy()
        env['BLADE_PYTHON_INTERPRETER'] = sys.executable
        os.chdir(self.work)
        p = subprocess.run(
            [self.blade, 'test', 'calc:calc_test', '--coverage'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            encoding='utf-8', env=env)
        self.assertEqual(p.returncode, 0,
                         'blade test --coverage (py) failed:\n%s' % p.stdout)
        report = os.path.join('build64_release_coverage',
                              'py_coverage_report', 'index.html')
        self.assertTrue(os.path.exists(report),
                        'no Python coverage report at %s\n%s' % (report, p.stdout))


if __name__ == '__main__':
    unittest.main()
