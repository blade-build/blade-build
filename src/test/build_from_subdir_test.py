# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration test: build when blade is invoked from a non-root directory.

blade must locate BLADE_ROOT by walking up from the current working
directory, so ``blade build :target`` works from inside a package
directory, not only from the workspace root. Regression guard for #857.
"""


import os
import shutil
import subprocess
import unittest


class BuildFromSubdirTest(unittest.TestCase):
    """Build a target with blade invoked from a workspace subdirectory."""

    def setUp(self):
        self.cur_dir = os.getcwd()
        here = os.path.dirname(os.path.abspath(__file__))
        # The blade wrapper lives at the repo root; this file is in src/test.
        self.blade = os.path.join(here, '..', '..', 'blade')
        self.root = os.path.join(here, 'testdata')
        self.build_dir = os.path.join(self.root, 'build64_release')
        shutil.rmtree(self.build_dir, ignore_errors=True)

    def tearDown(self):
        os.chdir(self.cur_dir)
        shutil.rmtree(self.build_dir, ignore_errors=True)

    def testBuildFromPackageDir(self):
        """Enter a package dir (not the workspace root) and build a target."""
        os.chdir(os.path.join(self.root, 'cc'))
        # ':uppercase' is the local-package shorthand; it only resolves if
        # blade found the workspace root above the current directory.
        p = subprocess.run(
            [self.blade, 'build', ':uppercase', '--generate-dynamic'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
        self.assertEqual(
            p.returncode, 0,
            'blade build from a subdir failed:\n%s' % p.stdout)
        # The artifact lands under the workspace-root build dir, proving blade
        # resolved BLADE_ROOT upward instead of treating cwd as the root.
        self.assertTrue(
            os.path.exists(os.path.join(self.build_dir, 'cc', 'libuppercase.a')),
            'expected artifact not produced; output:\n%s' % p.stdout)


if __name__ == '__main__':
    import blade_test
    blade_test.run(BuildFromSubdirTest)
