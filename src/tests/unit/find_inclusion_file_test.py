#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.

"""Unit tests for inclusion_check.Checker._find_inclusion_file.

Regression for the MSVC suffix mismatch: a source's inclusion file is named
`<src><obj_suffix>.H` (`.o.H` on GCC/clang, `.obj.H` on MSVC), so the finder
must use the toolchain's obj suffix instead of hardcoding `.o`.
"""

import os
import shutil
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import inclusion_check  # noqa: E402


class FindInclusionFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = 'pkg'
        self.name = 'lib'
        self.objs_dir = os.path.join(self.tmp, self.path, self.name + '.objs')
        os.makedirs(self.objs_dir)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _checker(self, obj_suffix: str) -> inclusion_check.Checker:
        target = {
            'type': 'cc_library', 'name': self.name, 'path': self.path,
            'key': '%s:%s' % (self.path, self.name), 'deps': [],
            'build_dir': self.tmp, 'source_location': 'pkg/BUILD:1',
            'expanded_srcs': [], 'expanded_hdrs': [],
            'declared_hdrs': set(), 'declared_incs': set(),
            'declared_genhdrs': set(), 'declared_genincs': set(),
            'hdrs_deps': {}, 'private_hdrs_deps': {}, 'allowed_undeclared_hdrs': {},
            'suppress': {}, 'severity': 'error', 'obj_suffix': obj_suffix,
        }
        return inclusion_check.Checker(target)

    def _touch(self, name: str) -> str:
        path = os.path.join(self.objs_dir, name)
        open(path, 'w').close()
        return path

    def test_source_gcc_suffix(self):
        c = self._checker('.o')
        expected = self._touch('foo.cc.o.H')
        self.assertEqual(c._find_inclusion_file('foo.cc', is_header=False), expected)

    def test_source_msvc_suffix(self):
        c = self._checker('.obj')
        expected = self._touch('foo.cc.obj.H')  # MSVC writes <src>.obj.H
        self.assertEqual(c._find_inclusion_file('foo.cc', is_header=False), expected)

    def test_source_msvc_does_not_match_dot_o(self):
        # The old hardcoded `.o.H` would not exist for an MSVC build; ensure the
        # finder returns '' (not a stale match) when only `.obj.H` would be wrong.
        c = self._checker('.obj')
        self._touch('foo.cc.o.H')  # wrong-suffix file present
        self.assertEqual(c._find_inclusion_file('foo.cc', is_header=False), '')

    def test_header_suffix_independent(self):
        for suffix in ('.o', '.obj'):
            c = self._checker(suffix)
            expected = self._touch('foo.h.H')
            self.assertEqual(c._find_inclusion_file('foo.h', is_header=True), expected)

    def test_default_suffix_is_dot_o(self):
        target = {
            'type': 'cc_library', 'name': self.name, 'path': self.path,
            'key': 'pkg:lib', 'deps': [], 'build_dir': self.tmp,
            'source_location': 'pkg/BUILD:1', 'expanded_srcs': [], 'expanded_hdrs': [],
            'declared_hdrs': set(), 'declared_incs': set(), 'declared_genhdrs': set(),
            'declared_genincs': set(), 'hdrs_deps': {}, 'private_hdrs_deps': {},
            'allowed_undeclared_hdrs': {}, 'suppress': {}, 'severity': 'error',
            # no 'obj_suffix' -> forward-compat default
        }
        c = inclusion_check.Checker(target)
        self.assertEqual(c.obj_suffix, '.o')


if __name__ == '__main__':
    unittest.main()
