#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the per-target ``generate_dynamic`` tri-state opt-out.

A ``dynamic_link`` binary/test forces ``generate_dynamic = True`` onto every
dependency so each is built as a shared library. A ``cc_library`` may opt out
with an explicit ``generate_dynamic = False`` (recorded as
``generate_dynamic_forced_off``); such a library is then linked statically even
into a dynamic_link binary. These tests pin that
``CcBinary._expand_deps_generation`` honors the opt-out.
"""

import os
import sys
import types
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402  (sys.path tweak above)


def _bare_binary(dynamic_link, expanded_deps, build_targets):
    """A ``CcBinary`` with just the fields ``_expand_deps_generation`` reads."""
    binary = cc_targets.CcBinary.__new__(cc_targets.CcBinary)
    binary.attr = {'dynamic_link': dynamic_link}
    binary.expanded_deps = expanded_deps
    binary.blade = mock.Mock()
    binary.blade.get_build_targets.return_value = build_targets
    return binary


def _dep(**attr):
    return types.SimpleNamespace(attr=dict(attr))


class WindowsDllBasenameTest(unittest.TestCase):
    """Package-path encoding for collision-free, flatten-able DLL names."""

    def test_encodes_package_path_with_dots(self):
        self.assertEqual(
            'common.net.rpc.dll',
            cc_targets._windows_dll_basename('common/net', 'rpc'))

    def test_top_level_target(self):
        self.assertEqual('foo.dll', cc_targets._windows_dll_basename('', 'foo'))

    def test_dotted_component_is_rejected(self):
        # 'a.b/c' vs 'a/b.c' would both encode to 'a.b.c' -> reject the ambiguity.
        with self.assertRaises(ValueError):
            cc_targets._windows_dll_basename('a.b/c', 'd')


class _DepStub:
    """A dependency exposing only what ``_dynamic_dependencies`` reads."""

    def __init__(self, path='pkg', files=None, data=None):
        self.path = path
        self._files = files or {}
        self.data = data or {}

    def _get_target_file(self, label):
        return self._files.get(label)


def _toolchain():
    tc = mock.Mock()
    tc.DYNAMIC_LIB_LABEL = 'so'
    tc.STATIC_LIB_LABEL = 'a'
    return tc


def _binary_with_deps(deps):
    binary = cc_targets.CcBinary.__new__(cc_targets.CcBinary)
    binary.expanded_deps = list(deps.keys())
    binary.blade = mock.Mock()
    binary.blade.get_build_targets.return_value = deps
    binary.blade.get_build_toolchain.return_value = _toolchain()
    return binary


class DynamicDependenciesTest(unittest.TestCase):
    """A dynamic_link binary must still link static-only (opted-out) deps."""

    def test_prefers_dynamic_library(self):
        deps = {'//a:lib': _DepStub(files={'so': 'build/a/liblib.so', 'a': 'build/a/liblib.a'})}
        _, usr_libs, _ = _binary_with_deps(deps)._dynamic_dependencies()
        self.assertEqual(['build/a/liblib.so'], usr_libs)

    def test_falls_back_to_static_when_no_dynamic(self):
        # generate_dynamic = False -> no shared library, only a static one.
        deps = {'//a:opted_out': _DepStub(files={'a': 'build/a/libopted_out.a'})}
        _, usr_libs, _ = _binary_with_deps(deps)._dynamic_dependencies()
        self.assertEqual(['build/a/libopted_out.a'], usr_libs)

    def test_header_only_dep_uses_incchk_result(self):
        deps = {'//a:hdr': _DepStub(files={'incchk.result': 'build/a/hdr.incchk.result'})}
        _, usr_libs, incchk_deps = _binary_with_deps(deps)._dynamic_dependencies()
        self.assertEqual([], usr_libs)
        self.assertEqual(['build/a/hdr.incchk.result'], incchk_deps)


class ExpandDepsGenerationTest(unittest.TestCase):
    def test_dynamic_link_forces_generate_dynamic_on_plain_deps(self):
        normal = _dep()
        binary = _bare_binary(True, ['//a:normal'], {'//a:normal': normal})
        binary._expand_deps_generation()
        self.assertIs(True, normal.attr['generate_dynamic'])

    def test_explicit_opt_out_is_not_forced_on(self):
        normal = _dep()
        opted_out = _dep(generate_dynamic=False, generate_dynamic_forced_off=True)
        binary = _bare_binary(
            True, ['//a:normal', '//a:opted_out'],
            {'//a:normal': normal, '//a:opted_out': opted_out})
        binary._expand_deps_generation()
        # The plain dep is forced on...
        self.assertIs(True, normal.attr['generate_dynamic'])
        # ...but the opted-out library stays False (never a shared library).
        self.assertIs(False, opted_out.attr['generate_dynamic'])

    def test_static_link_binary_touches_nothing(self):
        normal = _dep()
        binary = _bare_binary(False, ['//a:normal'], {'//a:normal': normal})
        binary._expand_deps_generation()
        self.assertNotIn('generate_dynamic', normal.attr)


if __name__ == '__main__':
    unittest.main()
