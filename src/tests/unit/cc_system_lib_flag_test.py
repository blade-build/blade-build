#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""A `#name` system-lib dep renders differently per toolchain on the link line.

GCC/Clang take `-lname`; MSVC's link.exe / lld-link take the import library as a
positional argument (`name.lib`) and reject `-lname`. Without this, a vcpkg
port's private system libs (issue #1322) -- and any plain `#advapi32` dep --
fail to link on MSVC.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.cc_targets import _system_lib_link_flag  # noqa: E402


class SystemLibLinkFlagTest(unittest.TestCase):

    def test_gcc_clang_uses_dash_l(self):
        self.assertEqual(_system_lib_link_flag('pthread', is_msvc=False), '-lpthread')

    def test_msvc_appends_dot_lib(self):
        self.assertEqual(_system_lib_link_flag('dbghelp', is_msvc=True), 'dbghelp.lib')

    def test_msvc_does_not_double_suffix(self):
        # A name already carrying .lib (any case) is passed through as-is.
        self.assertEqual(_system_lib_link_flag('shlwapi.lib', is_msvc=True),
                         'shlwapi.lib')
        self.assertEqual(_system_lib_link_flag('User32.LIB', is_msvc=True),
                         'User32.LIB')

    def test_absolute_path_passed_through(self):
        abs_lib = os.path.join(os.sep, 'abs', 'libfoo.a')
        self.assertEqual(_system_lib_link_flag(abs_lib, is_msvc=False), abs_lib)
        self.assertEqual(_system_lib_link_flag(abs_lib, is_msvc=True), abs_lib)


if __name__ == '__main__':
    unittest.main()
