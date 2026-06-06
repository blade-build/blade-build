#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for load_build_files._is_load_excluded_dir (issue #518).

"""Tests for the BUILD-file walker's dir-skip predicate.

Issue #518 asked blade to stop hardcoding the build-output directory
names (build32_debug / build64_release / ...) in the walker. The fix
is two-sided: ``Workspace.setup_build_dir`` drops a ``.bladeskip``
sentinel into the build dir so it gets skipped by the normal sentinel
walker; ``_is_load_excluded_dir`` then only filters dot-directories.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import load_build_files  # noqa: E402


class IsLoadExcludedDirTest(unittest.TestCase):
    """Pin the new minimal behavior: skip dot-dirs, nothing else by name."""

    def test_dot_git_skipped(self):
        self.assertTrue(load_build_files._is_load_excluded_dir('.git'))

    def test_dot_svn_skipped(self):
        self.assertTrue(load_build_files._is_load_excluded_dir('.svn'))

    def test_dot_vscode_skipped(self):
        self.assertTrue(load_build_files._is_load_excluded_dir('.vscode'))

    def test_dot_anything_skipped(self):
        # A dot-prefix has long been the convention for tool/state dirs;
        # we keep that.
        self.assertTrue(load_build_files._is_load_excluded_dir('.cache'))
        self.assertTrue(load_build_files._is_load_excluded_dir('.bladeskip_dir'))

    def test_build_dir_names_not_special_cased(self):
        """Regression for #518: the walker no longer treats
        ``build32_*``/``build64_*`` as magic. A directory named
        ``build64_release`` that lives in a user project should be
        walkable like any other dir; only the ``.bladeskip`` sentinel
        the workspace setup drops marks blade's own output dir."""
        self.assertFalse(load_build_files._is_load_excluded_dir('build64_release'))
        self.assertFalse(load_build_files._is_load_excluded_dir('build32_debug'))
        self.assertFalse(load_build_files._is_load_excluded_dir('build64_debug'))
        self.assertFalse(load_build_files._is_load_excluded_dir('build32_release'))

    def test_ordinary_dir_not_skipped(self):
        for d in ('src', 'flare', 'thirdparty', 'lib_release', 'tools'):
            self.assertFalse(load_build_files._is_load_excluded_dir(d),
                             msg=f'{d!r} should not be skipped')


class BuildDirsConstantRemovedTest(unittest.TestCase):
    """The pre-fix module exposed a hardcoded ``_BUILD_DIRS`` set; the
    fix removes it. A test pins that so a future refactor that
    accidentally re-introduces it surfaces clearly."""

    def test_build_dirs_constant_removed(self):
        self.assertFalse(hasattr(load_build_files, '_BUILD_DIRS'))


if __name__ == '__main__':
    unittest.main()
