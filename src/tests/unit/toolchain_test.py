#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.toolchain.

"""Unit tests for the ToolChain helper.

These tests mock out :func:`blade.util.run_command` so that the tests run on
any host without requiring a real compiler, and without caring about the
quirks of whichever vendor `gcc` happens to resolve to on the current
machine. The point is to pin down the pure decision logic of
``ToolChain.cc_is`` / ``ToolChain._detect_cc_vendor`` so that future changes
cannot silently regress the cross-vendor behaviour.
"""

import os
import sys
import unittest
from unittest import mock

# Make ``import blade.*`` resolve against the in-tree sources without
# requiring blade to be installed.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import toolchain  # noqa: E402  (sys.path tweak above)


# Representative banner lines copied from real compiler invocations.
_APPLE_CLANG_BANNER = (
    'Apple clang version 14.0.3 (clang-1403.0.22.14.1)\n'
    'Target: arm64-apple-darwin22.6.0\n'
)
_UPSTREAM_CLANG_BANNER = (
    'clang version 17.0.6\n'
    'Target: x86_64-pc-linux-gnu\n'
)
_GCC_BANNER = (
    'gcc (Ubuntu 11.4.0-1ubuntu1~22.04) 11.4.0\n'
    'Copyright (C) 2021 Free Software Foundation, Inc.\n'
)
_UNKNOWN_BANNER = 'Some hypothetical HPC compiler v9.9\n'


def _make_run_command(version_stdout, version_ok=True, dumpversion='14.0.3'):
    """Build a fake ``run_command`` dispatcher keyed on the argv shape."""

    def fake_run_command(argv, *args, **kwargs):
        # ToolChain calls run_command with (cc_path, '-dumpversion') and
        # (cc_path, '--version'); nothing else in __init__.
        if '-dumpversion' in argv:
            return (0, dumpversion, '')
        if '--version' in argv:
            rc = 0 if version_ok else 1
            return (rc, version_stdout, '')
        raise AssertionError('unexpected run_command argv: %r' % (argv,))

    return fake_run_command


class DetectCcVendorTest(unittest.TestCase):
    """Cover every branch of ToolChain._detect_cc_vendor."""

    def _build_toolchain(self, fake):
        with mock.patch.object(toolchain, 'run_command', side_effect=fake):
            return toolchain.ToolChain()

    def test_apple_clang_is_detected_as_clang(self):
        tc = self._build_toolchain(_make_run_command(_APPLE_CLANG_BANNER))
        self.assertEqual(tc._cc_vendor, 'clang')
        self.assertTrue(tc.cc_is('clang'))
        # Regression pin: Apple's `gcc` is Clang; cc_is('gcc') must NOT match.
        self.assertFalse(tc.cc_is('gcc'))

    def test_upstream_clang_is_detected_as_clang(self):
        tc = self._build_toolchain(_make_run_command(_UPSTREAM_CLANG_BANNER))
        self.assertEqual(tc._cc_vendor, 'clang')

    def test_real_gcc_is_detected_as_gcc(self):
        tc = self._build_toolchain(_make_run_command(_GCC_BANNER))
        self.assertEqual(tc._cc_vendor, 'gcc')
        self.assertTrue(tc.cc_is('gcc'))
        self.assertFalse(tc.cc_is('clang'))

    def test_unknown_banner_maps_to_unknown(self):
        tc = self._build_toolchain(_make_run_command(_UNKNOWN_BANNER))
        self.assertEqual(tc._cc_vendor, 'unknown')
        # Any vendor query against 'unknown' must be False so that callers
        # take the conservative branch.
        self.assertFalse(tc.cc_is('gcc'))
        self.assertFalse(tc.cc_is('clang'))

    def test_version_probe_failure_maps_to_unknown(self):
        tc = self._build_toolchain(
            _make_run_command(_GCC_BANNER, version_ok=False))
        self.assertEqual(tc._cc_vendor, 'unknown')
        self.assertFalse(tc.cc_is('gcc'))


class CcIsStrictEqualityTest(unittest.TestCase):
    """Pin cc_is semantics: exact match, no substring tricks."""

    def test_cc_is_rejects_partial_matches(self):
        # Directly construct a fake ToolChain without touching subprocess,
        # to exercise cc_is in isolation.
        tc = toolchain.ToolChain.__new__(toolchain.ToolChain)
        tc._cc_vendor = 'clang'
        self.assertTrue(tc.cc_is('clang'))
        self.assertFalse(tc.cc_is('clan'))
        self.assertFalse(tc.cc_is('clang++'))
        self.assertFalse(tc.cc_is(''))


if __name__ == '__main__':
    unittest.main()
