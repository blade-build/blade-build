#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for prebuilt_cc_library explicit lib paths (#1261).

`static_library` / `dynamic_library` give the archive/shared-lib paths directly
(relative to the target dir), overriding the name-convention lookup.
`import_library` is the Windows import `.lib` linked to use a `.dll` (#1357
phase 2): on MSVC it serves link-time dynamic linking while the `.dll` is the
runtime-only payload.

Expected paths are built with os.path.join so the comparisons hold on every
host (the resolver joins with the native separator).
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402

J = os.path.join


class _TC:
    static_lib_suffix = '.a'
    dynamic_lib_suffix = '.so'

    def __init__(self, vendor='gcc'):
        self._vendor = vendor

    def cc_is(self, vendor):
        return vendor == self._vendor


def _target(static_library=None, dynamic_library=None, import_library=None,
            libpath_pattern=None):
    t = cc_targets.PrebuiltCcLibrary.__new__(cc_targets.PrebuiltCcLibrary)
    t.path = 'pkg'
    t.attr = {
        'static_library': static_library,
        'dynamic_library': dynamic_library,
        'import_library': import_library,
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
            s, d, i = t._resolve_library_sources(_TC())
        self.assertEqual((J('pkg', 'libfoo.a'), None, None), (s, d, i))
        self.assertEqual([], t.errors)

    def test_explicit_both(self):
        t = _target(static_library='libfoo.a', dynamic_library='lib/libfoo.so')
        with mock.patch('os.path.exists', return_value=True):
            s, d, i = t._resolve_library_sources(_TC())
        self.assertEqual((J('pkg', 'libfoo.a'), J('pkg', 'lib/libfoo.so'), None),
                         (s, d, i))

    def test_explicit_missing_file_errors(self):
        # A set-but-missing explicit path is an error and resolves to None.
        t = _target(static_library='gone.a')
        with mock.patch('os.path.exists', return_value=False):
            s, _d, _i = t._resolve_library_sources(_TC())
        self.assertIsNone(s)
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
            s, d, i = t._resolve_library_sources(_TC())
        self.assertEqual(('pkg/lib64/libfoo.a', 'pkg/lib64/libfoo.so', None),
                         (s, d, i))
        self.assertEqual([], t.warnings)  # no libpath_pattern warning in convention mode

    def test_convention_mode_missing_one_kind_is_none(self):
        # In convention mode a kind that doesn't exist resolves to None.
        t = _target()
        t._library_source_path = mock.Mock(
            side_effect=lambda suf: 'pkg/lib64/libfoo' + suf)
        exists = lambda p: p.endswith('.a')  # only the static archive is present
        with mock.patch('os.path.exists', side_effect=exists):
            s, d, i = t._resolve_library_sources(_TC())
        self.assertEqual(('pkg/lib64/libfoo.a', None, None), (s, d, i))

    # --- Windows import_library (#1357 phase 2) ---

    def test_import_library_resolved_on_msvc(self):
        t = _target(dynamic_library='bin/foo.dll', import_library='lib/foo.lib')
        with mock.patch('os.path.exists', return_value=True):
            s, d, i = t._resolve_library_sources(_TC('msvc'))
        self.assertEqual((None, J('pkg', 'bin/foo.dll'), J('pkg', 'lib/foo.lib')),
                         (s, d, i))
        self.assertEqual([], t.errors)

    def test_dll_without_import_library_errors_on_msvc(self):
        t = _target(dynamic_library='bin/foo.dll')
        with mock.patch('os.path.exists', return_value=True):
            t._resolve_library_sources(_TC('msvc'))
        self.assertEqual(1, len(t.errors))
        self.assertIn('dynamic_library requires import_library', t.errors[0])

    def test_import_library_ignored_off_msvc(self):
        # import_library is a Windows concept; on gcc/clang it's not resolved.
        t = _target(dynamic_library='lib/libfoo.so', import_library='lib/foo.lib')
        with mock.patch('os.path.exists', return_value=True):
            s, d, i = t._resolve_library_sources(_TC('gcc'))
        self.assertEqual((None, J('pkg', 'lib/libfoo.so'), None), (s, d, i))
        self.assertEqual([], t.errors)

    def test_import_library_missing_file_errors_on_msvc(self):
        t = _target(import_library='lib/foo.lib')
        with mock.patch('os.path.exists', return_value=False):
            _s, _d, i = t._resolve_library_sources(_TC('msvc'))
        self.assertIsNone(i)
        self.assertEqual(1, len(t.errors))
        self.assertIn('import_library: file not found', t.errors[0])


class _SetupTC:
    """A toolchain stub for _setup wiring tests (MSVC)."""
    STATIC_LIB_LABEL = 'static'
    DYNAMIC_LIB_LABEL = 'dynamic'
    static_lib_suffix = '.lib'
    dynamic_lib_suffix = '.dll'

    def __init__(self, vendor='msvc'):
        self._vendor = vendor

    def cc_is(self, vendor):
        return vendor == self._vendor


class SetupImportLibraryTest(unittest.TestCase):
    """On MSVC, the import lib is the link target (DYNAMIC_LIB_LABEL) and the DLL
    is recorded as the runtime payload (windows_dll), mirroring blade's own
    generated DLLs."""

    def _target(self, **attrs):
        t = cc_targets.PrebuiltCcLibrary.__new__(cc_targets.PrebuiltCcLibrary)
        t.path = 'pkg'
        t.attr = {'static_library': None, 'dynamic_library': None,
                  'import_library': None, 'libpath_pattern': None}
        t.attr.update(attrs)
        t.data = {}
        t.errors = []
        t.error = t.errors.append
        t.warning = lambda *a: None
        t._target_files = {}
        t._add_target_file = lambda label, path: t._target_files.__setitem__(label, path)
        tc = _SetupTC()
        t.blade = mock.Mock()
        t.blade.get_build_toolchain.return_value = tc
        return t

    def test_import_and_dll(self):
        t = self._target(static_library='lib/foo.lib',
                         dynamic_library='bin/foo.dll',
                         import_library='lib/foo.dll.lib')
        with mock.patch('os.path.exists', return_value=True):
            t._setup()
        self.assertEqual(J('pkg', 'lib/foo.lib'), t._target_files['static'])
        # Dependents link the import lib, not the DLL.
        self.assertEqual(J('pkg', 'lib/foo.dll.lib'), t._target_files['dynamic'])
        # The DLL is the runtime payload the runner flattens into runfiles.
        self.assertEqual(J('pkg', 'bin/foo.dll'), t.data['windows_dll'])

    def test_import_only_serves_both_links(self):
        # An import lib with no static/DLL serves both static and dynamic links.
        t = self._target(import_library='lib/foo.lib')
        with mock.patch('os.path.exists', return_value=True):
            t._setup()
        self.assertEqual(J('pkg', 'lib/foo.lib'), t._target_files['static'])
        self.assertEqual(J('pkg', 'lib/foo.lib'), t._target_files['dynamic'])
        self.assertNotIn('windows_dll', t.data)


if __name__ == '__main__':
    unittest.main()
