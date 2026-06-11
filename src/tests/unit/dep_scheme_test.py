#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for the `<scheme>#<coordinate>` dependency parser (issue #1236).

"""Tests the provider-qualified dependency seam added as PR2 of vcpkg support.

`<scheme>#<coordinate>` (e.g. `vcpkg#fmt:fmt`) extends blade's `#name`
system-library family: a bare `#name` (empty scheme) stays an ambient system
lib, while a scheme before the `#` dispatches to a registered provider. PR2
adds only the generic parser + provider registry; the vcpkg provider that
resolves coordinates to real libraries lands in PR3, so no provider is
registered by default here -- the tests register a fake one to exercise the
seam.

`_unify_dep`/`_unify_scheme_dep` are called unbound against a Mock `self`,
which is enough for the parser branch (it only touches `self.error`, the
module-level registry, and -- for the non-scheme routing checks --
`self._add_system_library`).
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import target as target_mod  # noqa: E402
from blade.target import Target  # noqa: E402


class _Self:
    """Minimal stand-in for a Target with just what the parser touches."""

    def __init__(self):
        self.errors = []
        self.path = 'some/dir'

    def error(self, msg):
        self.errors.append(msg)


class DepSchemeRegistryTest(unittest.TestCase):
    """register_dep_scheme wires a handler that _unify_scheme_dep dispatches to."""

    def setUp(self):
        self._saved = dict(target_mod._dep_scheme_providers)

    def tearDown(self):
        target_mod._dep_scheme_providers.clear()
        target_mod._dep_scheme_providers.update(self._saved)

    def test_registered_provider_is_dispatched(self):
        calls = []

        def handler(referrer, coordinate):
            calls.append((referrer, coordinate))
            return 'fake#%s' % coordinate

        target_mod.register_dep_scheme('fake', handler)
        s = _Self()
        key = Target._unify_scheme_dep(s, 'fake#port:lib', 'fake', 'port:lib')
        self.assertEqual(key, 'fake#port:lib')
        self.assertEqual(calls, [(s, 'port:lib')])
        self.assertEqual(s.errors, [])

    def test_unknown_scheme_errors(self):
        s = _Self()
        key = Target._unify_scheme_dep(s, 'nope#x:y', 'nope', 'x:y')
        self.assertIsNone(key)
        self.assertEqual(len(s.errors), 1)
        self.assertIn('Unknown dependency scheme', s.errors[0])

    def test_invalid_scheme_spelling_errors(self):
        # Uppercase / leading digit are rejected before any provider lookup.
        for bad in ('Vcpkg', '1pkg', 'v_pkg'):
            s = _Self()
            key = Target._unify_scheme_dep(s, bad + '#x:y', bad, 'x:y')
            self.assertIsNone(key)
            self.assertEqual(len(s.errors), 1)
            self.assertIn('scheme', s.errors[0])

    def test_empty_coordinate_errors(self):
        s = _Self()
        key = Target._unify_scheme_dep(s, 'vcpkg#', 'vcpkg', '')
        self.assertIsNone(key)
        self.assertEqual(len(s.errors), 1)
        self.assertIn('empty coordinate', s.errors[0])

    def test_provider_returning_none_propagates(self):
        target_mod.register_dep_scheme('fake', lambda referrer, coord: None)
        s = _Self()
        self.assertIsNone(Target._unify_scheme_dep(s, 'fake#x', 'fake', 'x'))


class DepSchemeRoutingTest(unittest.TestCase):
    """_unify_dep routes scheme refs to _unify_scheme_dep and leaves the rest."""

    def test_scheme_ref_routed(self):
        s = mock.Mock()
        s._unify_scheme_dep.return_value = 'ROUTED'
        key = Target._unify_dep(s, 'vcpkg#fmt:fmt')
        self.assertEqual(key, 'ROUTED')
        s._unify_scheme_dep.assert_called_once_with('vcpkg#fmt:fmt', 'vcpkg', 'fmt:fmt')

    def test_bare_system_lib_not_routed(self):
        # Leading '#' (empty scheme) keeps the existing system-lib path.
        s = mock.Mock()
        s._add_system_library.return_value = None
        key = Target._unify_dep(s, '#pthread')
        self.assertEqual(key, '#:pthread')
        s._unify_scheme_dep.assert_not_called()
        s._add_system_library.assert_called_once_with('#:pthread', 'pthread')

    def test_normal_target_not_routed(self):
        s = mock.Mock()
        key = Target._unify_dep(s, '//foo/bar:baz')
        self.assertEqual(key, 'foo/bar:baz')
        s._unify_scheme_dep.assert_not_called()

    def test_first_hash_wins_for_split(self):
        # A '#' in the coordinate (none expected today, but be deterministic)
        # must not change where the scheme/coordinate boundary is taken.
        s = mock.Mock()
        s._unify_scheme_dep.return_value = 'R'
        Target._unify_dep(s, 'vcpkg#a#b')
        s._unify_scheme_dep.assert_called_once_with('vcpkg#a#b', 'vcpkg', 'a#b')


if __name__ == '__main__':
    unittest.main()
