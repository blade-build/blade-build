#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.cc_targets._generate_link_all_symbols_link_flags.

"""Unit tests for CcTarget._generate_link_all_symbols_link_flags.

The method emits linker flags that force every symbol of a static archive
to be pulled in — the idiom protoc-generated code relies on for descriptor
registration (proto_library sets ``link_all_symbols=True`` unconditionally),
and which thrift_library / fbthrift_library / lex_yacc_target reach for
the same way.

The flag spelling is platform-sensitive:

* GNU ld / gold / lld / mold, plus every BSD with a GNU-ld-compatible
  linker, speak ``-Wl,--whole-archive ... -Wl,--no-whole-archive``.
* Apple's ld64 / ld-prime — the only linker available to any macOS
  toolchain (Apple Clang, Homebrew GCC, Homebrew LLVM) because Mach-O
  has no GNU-ld port — rejects that spelling outright and needs
  ``-Wl,-force_load,<archive>`` once per archive instead.

These tests pin the branch selection so that a regression back to a
hard-coded GNU spelling immediately fails on Darwin CI (and vice versa).
"""

import os
import sys
import unittest
from unittest import mock

# Make ``import blade.*`` resolve against the in-tree sources without
# requiring blade to be installed.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402  (sys.path tweak above)


def _bare_cc_target():
    """Build a ``CcTarget`` instance bypassing __init__.

    The flag-generation logic under test reads nothing from ``self``,
    so we avoid the cost and dependencies of a full target construction.
    """
    return cc_targets.CcTarget.__new__(cc_targets.CcTarget)


class GenerateLinkAllSymbolsLinkFlagsTest(unittest.TestCase):
    """Cover every branch of the emitter."""

    def test_empty_input_returns_empty_regardless_of_platform(self):
        target = _bare_cc_target()
        # Emitter must short-circuit before consulting the platform so
        # that callers with no whole-archive libs don't accidentally
        # inject stray flags.
        with mock.patch.object(cc_targets.sys, 'platform', 'linux'):
            self.assertEqual([], target._generate_link_all_symbols_link_flags([]))
        with mock.patch.object(cc_targets.sys, 'platform', 'darwin'):
            self.assertEqual([], target._generate_link_all_symbols_link_flags([]))

    def test_linux_emits_gnu_whole_archive_pair(self):
        target = _bare_cc_target()
        libs = [
            'build64_release/suites/proto_basic/libcontact_proto.a',
            'build64_release/suites/thrift_basic/libping.a',
        ]
        with mock.patch.object(cc_targets.sys, 'platform', 'linux'):
            flags = target._generate_link_all_symbols_link_flags(libs)
        self.assertEqual(
            ['-Wl,--whole-archive'] + libs + ['-Wl,--no-whole-archive'],
            flags,
        )

    def test_darwin_emits_one_force_load_per_archive(self):
        target = _bare_cc_target()
        libs = [
            'build64_release/suites/proto_basic/libcontact_proto.a',
            'build64_release/suites/thrift_basic/libping.a',
        ]
        with mock.patch.object(cc_targets.sys, 'platform', 'darwin'):
            flags = target._generate_link_all_symbols_link_flags(libs)
        # One flag per archive, preserving order — link ordering matters
        # for symbol resolution and we must not silently collapse it.
        self.assertEqual(
            [
                '-Wl,-force_load,build64_release/suites/proto_basic/libcontact_proto.a',
                '-Wl,-force_load,build64_release/suites/thrift_basic/libping.a',
            ],
            flags,
        )

    def test_darwin_does_not_emit_gnu_whole_archive(self):
        # Regression pin: ld64 errors out with ``ld: unknown option:
        # --whole-archive`` if the GNU spelling leaks into the Darwin
        # branch. This test guards that boundary explicitly.
        target = _bare_cc_target()
        with mock.patch.object(cc_targets.sys, 'platform', 'darwin'):
            flags = target._generate_link_all_symbols_link_flags(['a.a'])
        joined = ' '.join(flags)
        self.assertNotIn('--whole-archive', joined)
        self.assertNotIn('--no-whole-archive', joined)

    def test_linux_single_lib_is_wrapped_once(self):
        target = _bare_cc_target()
        with mock.patch.object(cc_targets.sys, 'platform', 'linux'):
            flags = target._generate_link_all_symbols_link_flags(['x.a'])
        self.assertEqual(
            ['-Wl,--whole-archive', 'x.a', '-Wl,--no-whole-archive'],
            flags,
        )

    def test_unknown_platform_falls_back_to_gnu_spelling(self):
        # Anything other than Darwin keeps the GNU spelling — this is
        # the safe default for the long tail of Linux-like platforms
        # (``linux``, ``linux2``, ``freebsd14``, ``openbsd7``, ...).
        target = _bare_cc_target()
        for platform_value in ('linux', 'linux2', 'freebsd14', 'openbsd7'):
            with mock.patch.object(cc_targets.sys, 'platform', platform_value):
                flags = target._generate_link_all_symbols_link_flags(['y.a'])
            self.assertEqual(
                ['-Wl,--whole-archive', 'y.a', '-Wl,--no-whole-archive'],
                flags,
                msg='regressed on sys.platform=%r' % platform_value,
            )


if __name__ == '__main__':
    unittest.main()
