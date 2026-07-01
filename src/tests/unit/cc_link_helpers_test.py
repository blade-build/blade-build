#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the module-level cc link helpers (#1405 cgo).

`whole_archive_link_flags` was factored out of
`CcTarget._generate_link_all_symbols_link_flags` so non-cc consumers (go cgo)
can reuse it. Its output is platform-specific -- ld64 wants `-force_load` per
archive, MSVC `/WHOLEARCHIVE:`, GNU ld the `--whole-archive` group.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402  (sys.path tweak above)


class WholeArchiveLinkFlagsTest(unittest.TestCase):
    def setUp(self):
        self._platform = cc_targets.sys.platform
        self._osname = cc_targets.os.name

    def tearDown(self):
        cc_targets.sys.platform = self._platform
        cc_targets.os.name = self._osname

    def test_empty_is_empty(self):
        self.assertEqual([], cc_targets.whole_archive_link_flags([]))

    def test_darwin_force_load_per_archive(self):
        cc_targets.sys.platform = 'darwin'
        cc_targets.os.name = 'posix'
        self.assertEqual(
            ['-Wl,-force_load,a.a', '-Wl,-force_load,b.a'],
            cc_targets.whole_archive_link_flags(['a.a', 'b.a']))

    def test_windows_wholearchive(self):
        cc_targets.sys.platform = 'win32'
        cc_targets.os.name = 'nt'
        self.assertEqual(
            ['/WHOLEARCHIVE:a.lib'],
            cc_targets.whole_archive_link_flags(['a.lib']))

    def test_gnu_group_wraps_once(self):
        cc_targets.sys.platform = 'linux'
        cc_targets.os.name = 'posix'
        self.assertEqual(
            ['-Wl,--whole-archive', 'a.a', 'b.a', '-Wl,--no-whole-archive'],
            cc_targets.whole_archive_link_flags(['a.a', 'b.a']))


if __name__ == '__main__':
    unittest.main()
