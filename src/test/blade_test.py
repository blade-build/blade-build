# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <phongchen@tencent.com>
# Date:   October 20, 2011

"""
 This is the main test module for all targets.
"""

import io
import os
import shutil
import subprocess
import sys
import unittest


# pylint: disable=attribute-defined-outside-init
class TargetTest(unittest.TestCase):
    """base class Test."""

    def doSetUp(self, path, target='...', full_targets=None):
        """setup method."""
        if full_targets:
            self.targets = full_targets
        else:
            self.targets = '%s:%s' % (path, target)
        self.target_path = path
        self.cur_dir = os.getcwd()
        self.blade_path = '../../blade'
        self.working_dir = '.'
        self.current_building_path = 'build64_release'
        self.current_source_dir = '.'
        self.build_output = []
        self.build_output_file = 'build_output.txt'
        self.build_error = []
        self.build_error_file = 'build_error.txt'
        os.chdir('testdata')
        self.removeTree('build64_release')

    def tearDown(self):
        """tear down method."""
        self.doTearDown()
        os.chdir(self.cur_dir)

    def doTearDown(self):
        """tear down method."""

    def removeTree(self, path):
        try:
            shutil.rmtree('build64_release', ignore_errors=True)
        except OSError as e:
            print(e)

    def removeFile(self, path):
        self.removeTree(path)

    def runBlade(self, command='build', extra_args='', print_error=True):
        # We can use pipe to capture stdout, but keep the output file make it
        # easy debugging.
        p = subprocess.Popen(
            '../../../blade %s %s --generate-dynamic --verbose %s > %s 2> %s' % (
                command, self.targets, extra_args, self.build_output_file, self.build_error_file),
            shell=True)
        try:
            p.wait()
            self.build_output = io.open(self.build_output_file, encoding='utf-8').readlines()
            self.build_error = io.open(self.build_error_file, encoding='utf-8').readlines()
            if p.returncode != 0 and print_error:
                sys.stderr.write('Exit with: %d\nstdout:\n%s\nstderr:\n%s\n' % (
                    p.returncode, ''.join(self.build_output), ''.join(self.build_error)))
            return p.returncode == 0
        except Exception:  # pylint: disable=broad-except
            sys.stderr.write('Failed while dry running:\n%s\n' % str(sys.exc_info()))
        return False

    def dryRun(self, command='build', extra_args=''):
        return self.runBlade(command, '--dry-run ' + extra_args)

    def printOutput(self):
        """Helper method for debugging"""
        print(''.join(self.build_output))

    def findBuildOutput(self, kwlist, file='stdout'):
        if not isinstance(kwlist, list):
            kwlist = [kwlist]
        output = self.build_error if file == 'stderr' else self.build_output
        for lineno, line in enumerate(output):
            for kw in kwlist:
                if kw not in line:
                    break
            else:
                return line, lineno
        self.assertFalse('%s not found' % kwlist)
        return '', 0

    def findCommandAndLine(self, kwlist):
        return self.findBuildOutput(kwlist, file='stdout')

    def findCommand(self, kwlist):
        return self.findCommandAndLine(kwlist)[0]

    def inBuildOutput(self, kwlist):
        return self.findCommand(kwlist)

    def inBuildError(self, kwlist):
        return self.findBuildOutput(kwlist, file='stderr')[0]

    def _assertCxxCommonFlags(self, cmdline):
        self.assertIn('-g', cmdline)
        self.assertIn('-fPIC', cmdline)

    def _assertCxxWarningFlags(self, cmdline):
        self.assertIn('-Wall -Wextra', cmdline)
        self.assertIn('-Wframe-larger-than=69632', cmdline)
        self.assertIn('-Werror=vla', cmdline)

    def _assertCxxNoWarningFlags(self, cmdline):
        self.assertNotIn('-Wall -Wextra', cmdline)
        self.assertNotIn('-Wframe-larger-than=69632', cmdline)
        self.assertNotIn('-Werror=overloaded-virtual', cmdline)

    def assertCxxFlags(self, cmdline):
        self._assertCxxCommonFlags(cmdline)
        self._assertCxxWarningFlags(cmdline)

    def assertNoWarningCxxFlags(self, cmdline):
        self._assertCxxCommonFlags(cmdline)
        self._assertCxxNoWarningFlags(cmdline)

    def assertLinkFlags(self, cmdline):
        self.assertNotIn('-static-libgcc -static-libstdc++', cmdline)

    def assertStaticLinkFlags(self, cmdline):
        self.assertNotIn('-shared', cmdline)

    def assertDynamicLinkFlags(self, cmdline):
        self.assertIn('-shared', cmdline)


def run(class_name):
    suite_test = unittest.TestSuite()
    suite_test.addTests(
        [unittest.defaultTestLoader.loadTestsFromTestCase(class_name)])
    runner = unittest.TextTestRunner()
    result = runner.run(suite_test)
    if not result.wasSuccessful():
        sys.exit(1)
