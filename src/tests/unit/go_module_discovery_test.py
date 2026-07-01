#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for go_targets._find_module_dir (module discovery, #1405).

The walker resolves a target's owning Go module as the nearest `go.mod` at or
above the target dir, checked relative to the current directory (the workspace
root during analysis). Returns the workspace-relative module dir ('' for the
root module) or None.
"""

import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.go_targets import _find_module_dir  # noqa: E402


class FindModuleDirTest(unittest.TestCase):
    def setUp(self):
        self.cur = os.getcwd()
        self.work = tempfile.mkdtemp(prefix='blade_go_mod_')
        os.chdir(self.work)  # analysis runs from the workspace root

    def tearDown(self):
        os.chdir(self.cur)
        import shutil
        shutil.rmtree(self.work, ignore_errors=True)

    def _mkgomod(self, reldir):
        d = os.path.join(self.work, reldir) if reldir else self.work
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, 'go.mod'), 'w').close()

    def test_root_module_from_root(self):
        self._mkgomod('')
        self.assertEqual(_find_module_dir(''), '')

    def test_root_module_from_subdir(self):
        self._mkgomod('')
        os.makedirs('a/b/c', exist_ok=True)
        self.assertEqual(_find_module_dir('a/b/c'), '')

    def test_nearest_module_wins(self):
        self._mkgomod('')        # root module
        self._mkgomod('svc')     # nested module
        os.makedirs('svc/cmd', exist_ok=True)
        self.assertEqual(_find_module_dir('svc/cmd'), 'svc')
        self.assertEqual(_find_module_dir('svc'), 'svc')

    def test_module_in_subdir_only(self):
        self._mkgomod('svc')     # no root go.mod
        os.makedirs('svc/pkg', exist_ok=True)
        self.assertEqual(_find_module_dir('svc/pkg'), 'svc')

    def test_no_module_found(self):
        os.makedirs('a/b', exist_ok=True)
        self.assertIsNone(_find_module_dir('a/b'))
        self.assertIsNone(_find_module_dir(''))


if __name__ == '__main__':
    unittest.main()
