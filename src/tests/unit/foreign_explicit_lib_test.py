#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for foreign_cc_library explicit lib paths (#1262).

`static_library` / `dynamic_library` / `import_library` give the foreign build's
output paths (relative to install_dir, under the build tree), overriding the
`lib_dir`/`has_dynamic` name convention. Unlike a prebuilt these are generated,
so paths are declared, not probed.
"""

import os
import sys
import unittest
from typing import cast
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402
from blade.toolchain import ToolChain  # noqa: E402

J = os.path.join  # build expected paths with the native separator


class _FakeToolChain:
    static_lib_suffix = '.a'
    dynamic_lib_suffix = '.so'
    all_dynamic_lib_suffixes = ('.so',)
    lib_prefix = 'lib'

    def __init__(self, vendor='gcc'):
        self._vendor = vendor

    def cc_is(self, vendor):
        return vendor == self._vendor


def _tc(vendor='gcc') -> ToolChain:
    return cast(ToolChain, _FakeToolChain(vendor))


def _foreign(static=None, dynamic=None, importlib=None,
             install_dir='inst', has_dynamic=False):
    t = cc_targets.ForeignCcLibrary.__new__(cc_targets.ForeignCcLibrary)
    t.name = 'foo'
    t.attr = {
        'install_dir': install_dir, 'lib_dir': 'lib', 'has_dynamic': has_dynamic,
        'static_library': static, 'dynamic_library': dynamic,
        'import_library': importlib,
    }
    # Outputs live under the build tree; fake the build-dir prefix.
    t._target_file_path = lambda p: os.path.join('BD', p)
    t.errors = []
    t.error = t.errors.append
    return t


class ForeignResolveSourcesTest(unittest.TestCase):
    def test_explicit_static_and_dynamic(self):
        t = _foreign(static='lib/libfoo.a', dynamic='lib/libfoo.so')
        s, d, i = t._resolve_library_sources(_tc())
        self.assertEqual(
            (J('BD', 'inst', 'lib/libfoo.a'), J('BD', 'inst', 'lib/libfoo.so'), None),
            (s, d, i))
        self.assertEqual([], t.errors)

    def test_explicit_import_only_on_msvc(self):
        # import_library is resolved on MSVC, ignored elsewhere.
        t = _foreign(static='lib/foo.lib', dynamic='bin/foo.dll',
                     importlib='lib/foo.lib')
        _s, _d, i = t._resolve_library_sources(_tc('msvc'))
        self.assertEqual(J('BD', 'inst', 'lib/foo.lib'), i)
        # Non-MSVC: import ignored, no error (the .so is the link target).
        t2 = _foreign(static='lib/libfoo.a', importlib='lib/foo.lib')
        _s, _d, i2 = t2._resolve_library_sources(_tc('gcc'))
        self.assertIsNone(i2)

    def test_msvc_dynamic_without_import_errors(self):
        t = _foreign(dynamic='bin/foo.dll')
        t._resolve_library_sources(_tc('msvc'))
        self.assertEqual(1, len(t.errors))
        self.assertIn('import_library', t.errors[0])

    def test_convention_when_no_explicit(self):
        # No explicit attrs -> name convention via _library_full_path.
        t = _foreign(install_dir='inst', has_dynamic=True)
        t.blade = mock.Mock()
        t.blade.get_build_toolchain.return_value = _FakeToolChain()
        s, d, i = t._resolve_library_sources(_tc())
        self.assertEqual(J('BD', 'inst', 'lib', 'libfoo.a'), s)
        self.assertEqual(J('BD', 'inst', 'lib', 'libfoo.so'), d)
        self.assertIsNone(i)

    def test_convention_static_only_when_not_has_dynamic(self):
        t = _foreign(install_dir='inst', has_dynamic=False)
        t.blade = mock.Mock()
        t.blade.get_build_toolchain.return_value = _FakeToolChain()
        s, d, _i = t._resolve_library_sources(_tc())
        self.assertEqual(J('BD', 'inst', 'lib', 'libfoo.a'), s)
        self.assertIsNone(d)


class _NinjaTC:
    """Toolchain stub for _ninja_rules wiring tests (MSVC)."""
    STATIC_LIB_LABEL = 'a'
    DYNAMIC_LIB_LABEL = 'so'
    static_lib_suffix = '.lib'
    dynamic_lib_suffix = '.dll'
    all_dynamic_lib_suffixes = ('.dll',)
    lib_prefix = ''

    def __init__(self, vendor='msvc'):
        self._vendor = vendor

    def cc_is(self, vendor):
        return vendor == self._vendor


class ForeignNinjaRulesMsvcTest(unittest.TestCase):
    """_ninja_rules drives the shared link helper: on MSVC the import lib is the
    link target and the produced DLL is the runtime payload (windows_dll), linked
    in place (no copy)."""

    def _foreign(self, **attrs):
        t = cc_targets.ForeignCcLibrary.__new__(cc_targets.ForeignCcLibrary)
        t.name = 'foo'
        t.attr = {'install_dir': 'inst', 'lib_dir': 'lib', 'has_dynamic': False,
                  'static_library': None, 'dynamic_library': None,
                  'import_library': None}
        t.attr.update(attrs)
        t.data = {}
        t.errors = []
        t.error = t.errors.append
        t._target_file_path = lambda p: os.path.join('BD', p)
        t.target_files = {}
        t._add_target_file = lambda label, path: t.target_files.__setitem__(label, path)
        t._add_default_target_file = t._add_target_file
        t._soname_of = lambda p: None  # Windows: no soname
        t.emitted_syms = []
        t._emit_archive_syms = t.emitted_syms.append
        t.blade = mock.Mock()
        t.blade.get_build_toolchain.return_value = _NinjaTC()
        return t

    def test_import_and_dll_no_static(self):
        # Typical Windows foreign build: a .dll + its import .lib, no archive.
        t = self._foreign(dynamic_library='lib/foo.dll', import_library='lib/foo.lib')
        t._ninja_rules()
        imp = J('BD', 'inst', 'lib/foo.lib')
        dll = J('BD', 'inst', 'lib/foo.dll')
        self.assertEqual(imp, t.target_files['so'])   # link the import lib
        self.assertEqual(imp, t.target_files['a'])     # serves static link too
        self.assertEqual(dll, t.data['windows_dll'])   # DLL is the runtime payload
        self.assertEqual([imp], t.emitted_syms)        # .syms from the link source
        self.assertEqual([], t.errors)

    def test_static_and_import_and_dll(self):
        t = self._foreign(static_library='lib/foo_s.lib',
                          dynamic_library='lib/foo.dll',
                          import_library='lib/foo.lib')
        t._ninja_rules()
        self.assertEqual(J('BD', 'inst', 'lib/foo_s.lib'), t.target_files['a'])
        self.assertEqual(J('BD', 'inst', 'lib/foo.lib'), t.target_files['so'])
        self.assertEqual(J('BD', 'inst', 'lib/foo.dll'), t.data['windows_dll'])
        # .syms come from the static archive (the static-link source).
        self.assertEqual([J('BD', 'inst', 'lib/foo_s.lib')], t.emitted_syms)


if __name__ == '__main__':
    unittest.main()
