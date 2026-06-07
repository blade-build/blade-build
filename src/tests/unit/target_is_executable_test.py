#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the Target.is_executable class attribute (#647).

`blade run` and run_target() gate on whether a target is executable. This
used to be a hardcoded type-name list in BinaryRunner; it now lives on the
target classes as the ``is_executable`` attribute. These tests pin which
target types are executable (binaries and tests) and which are not
(libraries), including the values inherited by subclasses.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402
from blade import java_targets  # noqa: E402
from blade import py_targets  # noqa: E402
from blade import scala_targets  # noqa: E402
from blade import sh_test_target  # noqa: E402
from blade.target import Target  # noqa: E402


class TargetIsExecutableTest(unittest.TestCase):
    """Pin the executable/non-executable classification per target type."""

    def test_base_target_is_not_executable(self):
        self.assertFalse(Target.is_executable)

    def test_executable_targets(self):
        # Binaries and tests are runnable. Tests inherit the flag from their
        # binary base class (CcTest<-CcBinary, JavaTest<-JavaBinary,
        # PythonTest<-PythonBinary).
        for cls in (cc_targets.CcBinary, cc_targets.CcTest,
                    java_targets.JavaBinary, java_targets.JavaTest,
                    py_targets.PythonBinary, py_targets.PythonTest,
                    scala_targets.ScalaTest, sh_test_target.ShellTest):
            self.assertTrue(cls.is_executable,
                            '%s should be executable' % cls.__name__)

    def test_non_executable_targets(self):
        # Libraries are not runnable, including those that share a base with
        # an executable type (e.g. PythonBinary<-PythonLibrary).
        for cls in (cc_targets.CcLibrary,
                    java_targets.JavaLibrary,
                    py_targets.PythonLibrary,
                    scala_targets.ScalaLibrary,
                    scala_targets.ScalaFatLibrary):
            self.assertFalse(cls.is_executable,
                             '%s should not be executable' % cls.__name__)


if __name__ == '__main__':
    unittest.main()
