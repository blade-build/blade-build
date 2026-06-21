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
        self.assertEqual(('BD/inst/lib/libfoo.a', 'BD/inst/lib/libfoo.so', None),
                         (s, d, i))
        self.assertEqual([], t.errors)

    def test_explicit_import_only_on_msvc(self):
        # import_library is resolved on MSVC, ignored elsewhere.
        t = _foreign(static='lib/foo.lib', dynamic='bin/foo.dll',
                     importlib='lib/foo.lib')
        _s, _d, i = t._resolve_library_sources(_tc('msvc'))
        self.assertEqual('BD/inst/lib/foo.lib', i)
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
        self.assertEqual('BD/inst/lib/libfoo.a', s)
        self.assertEqual('BD/inst/lib/libfoo.so', d)
        self.assertIsNone(i)

    def test_convention_static_only_when_not_has_dynamic(self):
        t = _foreign(install_dir='inst', has_dynamic=False)
        t.blade = mock.Mock()
        t.blade.get_build_toolchain.return_value = _FakeToolChain()
        s, d, _i = t._resolve_library_sources(_tc())
        self.assertEqual('BD/inst/lib/libfoo.a', s)
        self.assertIsNone(d)


if __name__ == '__main__':
    unittest.main()
