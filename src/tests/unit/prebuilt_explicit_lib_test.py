#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for prebuilt_cc_library explicit lib paths (#1261).

`static_library` / `dynamic_library` give the archive/shared-lib paths directly
(relative to the target dir), overriding the name-convention lookup.
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402


class _TC:
    static_lib_suffix = '.a'
    dynamic_lib_suffix = '.so'


def _target(static_library=None, dynamic_library=None, libpath_pattern=None):
    t = cc_targets.PrebuiltCcLibrary.__new__(cc_targets.PrebuiltCcLibrary)
    t.path = 'pkg'
    t.attr = {
        'static_library': static_library,
        'dynamic_library': dynamic_library,
        'libpath_pattern': libpath_pattern,
    }
    t.errors = []
    t.warnings = []
    t.error = t.errors.append
    t.warning = t.warnings.append
    return t


class ResolveLibrarySourcesTest(unittest.TestCase):
    def test_explicit_static_only(self):
        t = _target(static_library='libfoo.a')
        with mock.patch('os.path.exists', return_value=True):
            s, d, hs, hd = t._resolve_library_sources(_TC())
        self.assertEqual(('pkg/libfoo.a', None, True, False), (s, d, hs, hd))
        self.assertEqual([], t.errors)

    def test_explicit_both(self):
        t = _target(static_library='libfoo.a', dynamic_library='lib/libfoo.so')
        with mock.patch('os.path.exists', return_value=True):
            s, d, hs, hd = t._resolve_library_sources(_TC())
        self.assertEqual(('pkg/libfoo.a', 'pkg/lib/libfoo.so', True, True),
                         (s, d, hs, hd))

    def test_explicit_missing_file_errors(self):
        t = _target(static_library='gone.a')
        with mock.patch('os.path.exists', return_value=False):
            _s, _d, hs, _hd = t._resolve_library_sources(_TC())
        self.assertFalse(hs)
        self.assertEqual(1, len(t.errors))
        self.assertIn('not found', t.errors[0])

    def test_explicit_ignores_libpath_pattern_with_warning(self):
        t = _target(static_library='libfoo.a', libpath_pattern='lib64')
        with mock.patch('os.path.exists', return_value=True):
            t._resolve_library_sources(_TC())
        self.assertEqual(1, len(t.warnings))
        self.assertIn('libpath_pattern is ignored', t.warnings[0])

    def test_convention_mode_uses_name_lookup(self):
        # No explicit attrs -> falls back to _library_source_path (convention).
        t = _target()
        t._library_source_path = mock.Mock(
            side_effect=lambda suf: 'pkg/lib64/libfoo' + suf)
        with mock.patch('os.path.exists', return_value=True):
            s, d, hs, hd = t._resolve_library_sources(_TC())
        self.assertEqual(('pkg/lib64/libfoo.a', 'pkg/lib64/libfoo.so', True, True),
                         (s, d, hs, hd))
        self.assertEqual([], t.warnings)  # no libpath_pattern warning in convention mode


if __name__ == '__main__':
    unittest.main()
