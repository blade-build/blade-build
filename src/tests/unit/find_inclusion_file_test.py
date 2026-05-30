#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.

"""Unit tests for inclusion_check.Checker._find_inclusion_file.

The per-source/header inclusion stack is named `<file>.incstk`, independent of
the object-file suffix (`.o` on GCC/clang, `.obj` on MSVC), so the finder uses
the same name for sources and headers regardless of toolchain.
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
        self.tmp = tempfile.mkdtemp().replace('\\', '/')
        self.path = 'pkg'
        self.name = 'lib'
        self.objs_dir = '/'.join([self.tmp, self.path, self.name + '.objs'])
        os.makedirs(self.objs_dir)
        self.checker = self._checker()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _checker(self) -> inclusion_check.Checker:
        target = {
            'type': 'cc_library', 'name': self.name, 'path': self.path,
            'key': '%s:%s' % (self.path, self.name), 'deps': [],
            'build_dir': self.tmp, 'source_location': 'pkg/BUILD:1',
            'expanded_srcs': [], 'expanded_hdrs': [],
            'declared_hdrs': set(), 'declared_incs': set(),
            'declared_genhdrs': set(), 'declared_genincs': set(),
            'hdrs_deps': {}, 'private_hdrs_deps': {}, 'allowed_undeclared_hdrs': {},
            'suppress': {}, 'severity': 'error',
        }
        return inclusion_check.Checker(target)

    def _touch(self, name: str) -> str:
        path = self.objs_dir + '/' + name
        open(path, 'w').close()
        return path

    def test_source_inclusion_file(self):
        expected = self._touch('foo.cc.incstk')
        self.assertEqual(self.checker._find_inclusion_file('foo.cc'), expected)

    def test_header_inclusion_file(self):
        expected = self._touch('foo.h.incstk')
        self.assertEqual(self.checker._find_inclusion_file('foo.h'), expected)

    def test_source_in_subdir(self):
        os.makedirs(self.objs_dir + '/sub')
        expected = self._touch('sub/foo.cc.incstk')
        self.assertEqual(self.checker._find_inclusion_file('sub/foo.cc'), expected)

    def test_missing_returns_empty(self):
        # No `.incstk` written for this source -> not found.
        self.assertEqual(self.checker._find_inclusion_file('foo.cc'), '')

    def test_legacy_obj_suffix_name_not_matched(self):
        # The old `<src>.o.H` / `<src>.obj.H` names must not be picked up.
        self._touch('foo.cc.o.H')
        self._touch('foo.cc.obj.H')
        self.assertEqual(self.checker._find_inclusion_file('foo.cc'), '')


if __name__ == '__main__':
    unittest.main()
