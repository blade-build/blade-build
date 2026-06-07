# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration test for the ``blade root`` subcommand (#528).

``blade root`` prints the absolute workspace root directory and exits,
with clean stdout (so ``cd "$(blade root)"`` works) regardless of which
subdirectory it is invoked from.
"""


import os
import subprocess
import unittest


class RootCommandTest(unittest.TestCase):
    """Verify ``blade root`` prints the workspace root from any directory."""

    def setUp(self):
        self.cur_dir = os.getcwd()
        here = os.path.dirname(os.path.abspath(__file__))
        self.blade = os.path.join(here, '..', '..', 'blade')
        self.root = os.path.join(here, 'testdata')

    def tearDown(self):
        os.chdir(self.cur_dir)

    def _blade_root(self, from_dir):
        os.chdir(from_dir)
        p = subprocess.run(
            [self.blade, 'root'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
        self.assertEqual(p.returncode, 0, 'blade root failed:\n%s' % p.stderr)
        return p.stdout

    def testRootFromWorkspaceRoot(self):
        out = self._blade_root(self.root)
        self.assertEqual(out.strip(), os.path.abspath(self.root))

    def testRootFromSubdir(self):
        # Invoked from a package dir, stdout must still be exactly the root.
        out = self._blade_root(os.path.join(self.root, 'cc'))
        self.assertEqual(out.strip(), os.path.abspath(self.root))

    def testRootRejectsTargets(self):
        os.chdir(self.root)
        p = subprocess.run(
            [self.blade, 'root', '//cc:uppercase'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
        self.assertNotEqual(p.returncode, 0)


if __name__ == '__main__':
    import blade_test
    blade_test.run(RootCommandTest)
