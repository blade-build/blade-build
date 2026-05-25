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
import unittest  # lgtm[py/import-and-import-from]
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
    """Cover every branch of GccToolChain._detect_cc_vendor."""

    def _build_toolchain(self, fake):
        with mock.patch.object(toolchain, 'run_command', side_effect=fake):
            return toolchain.GccToolChain()

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


class GccToolChainInitTest(unittest.TestCase):
    """Test GccToolChain constructor with explicit params."""

    def _build(self, **kwargs):
        with mock.patch.object(toolchain, 'run_command',
                               side_effect=_make_run_command(_GCC_BANNER)):
            return toolchain.GccToolChain(**kwargs)

    def test_default_kind_is_gcc(self):
        tc = self._build()
        self.assertEqual(tc._kind, 'gcc')

    def test_explicit_kind_is_stored(self):
        tc = self._build(kind='clang')
        self.assertEqual(tc._kind, 'clang')

    def test_target_linux_native_suffixes(self):
        tc = self._build(target='linux')
        self.assertEqual(tc.exe_suffix, '')
        self.assertEqual(tc.lib_prefix, 'lib')
        self.assertEqual(tc.dynamic_lib_suffix, '.so')
        self.assertIsNone(tc.tool('rc'))

    def test_target_darwin_suffixes(self):
        tc = self._build(target='darwin')
        self.assertEqual(tc.exe_suffix, '')
        self.assertEqual(tc.lib_prefix, 'lib')
        self.assertEqual(tc.dynamic_lib_suffix, '.dylib')

    def test_target_windows_suffixes(self):
        tc = self._build(target='windows')
        self.assertEqual(tc.exe_suffix, '.exe')
        self.assertEqual(tc.lib_prefix, '')
        self.assertEqual(tc.dynamic_lib_suffix, '.dll')
        self.assertEqual(tc.tool('rc'), 'windres')

    def test_tool_cc_returns_cc_path(self):
        tc = self._build(cc='/my/gcc')
        self.assertEqual(tc.tool('cc'), '/my/gcc')

    def test_tool_as_is_none_for_gcc_family(self):
        tc = self._build()
        self.assertIsNone(tc.tool('as'))


class DefaultTargetForKindTest(unittest.TestCase):
    """Test _default_target_for_kind helper."""

    def test_gcc_defaults_to_host(self):
        target = toolchain._default_target_for_kind('gcc')
        self.assertIn(target, ('linux', 'darwin', 'windows'))

    def test_mingw_always_windows(self):
        self.assertEqual(toolchain._default_target_for_kind('mingw'), 'windows')

    def test_cygwin_always_windows(self):
        self.assertEqual(toolchain._default_target_for_kind('cygwin'), 'windows')

    def test_msvc_always_windows(self):
        self.assertEqual(toolchain._default_target_for_kind('msvc'), 'windows')


class ResolveToolTest(unittest.TestCase):
    """Test _resolve_tool helper."""

    def test_bare_tool_name_fallback(self):
        result = toolchain._resolve_tool('', '', 'gcc')
        self.assertTrue(result)  # gcc should be found on PATH or fallback

    def test_tool_prefix_is_prepended(self):
        result = toolchain._resolve_tool('', 'arm-linux-gnueabihf-', 'gcc')
        self.assertIn('arm-linux-gnueabihf-gcc', result)

    def test_prefix_scoped_no_path_fallback(self):
        """When prefix is set, which() must NOT be used — only prefix paths."""
        result = toolchain._resolve_tool('/nonexistent/prefix', '', 'gcc')
        self.assertIn('gcc', result)

    def test_prefix_with_tool_prefix(self):
        """Prefix + tool_prefix: result includes the prefixed tool name."""
        result = toolchain._resolve_tool('/nonexistent/cross', 'arm-linux-gnueabihf-', 'gcc')
        self.assertEqual(result, 'arm-linux-gnueabihf-gcc')


class ToolMethodTest(unittest.TestCase):
    """Test unified tool(key) method."""

    def test_tool_with_unknown_key_returns_none(self):
        tc = toolchain.ToolChain.__new__(toolchain.ToolChain)
        tc._tools = {}
        self.assertIsNone(tc.tool('unknown_key'))

    def test_tool_with_known_key_returns_value(self):
        tc = toolchain.ToolChain.__new__(toolchain.ToolChain)
        tc._tools = {'rc': '/path/to/rc.exe'}
        self.assertEqual(tc.tool('rc'), '/path/to/rc.exe')


class CreateToolchainMultiConfigTest(unittest.TestCase):
    """Test create_toolchain with multiple named cc_toolchain_config entries."""

    def setUp(self):
        # Build a fake config section with named entries, mimicking what
        # cc_toolchain_config(name=...) produces. All entries, including the
        # unnamed default, are stored as dicts keyed by name.
        self._section = {
            '': {
                'name': '',
                'kind': '',
                'prefix': '',
                'tool_prefix': '',
                'target': '',
                'cc': '', 'cxx': '', 'ld': '', 'ar': '',
                'msvc_version': 'auto', 'target_arch': 'auto',
            },
            'gcc-13': {
                'name': 'gcc-13',
                'kind': 'gcc',
                'prefix': '/opt/gcc-13',
                'tool_prefix': '',
                'target': '',
                'cc': '', 'cxx': '', 'ld': '', 'ar': '',
                'msvc_version': 'auto', 'target_arch': 'auto',
            },
            'clang-17': {
                'name': 'clang-17',
                'kind': 'clang',
                'prefix': '/opt/clang-17',
                'tool_prefix': '',
                'target': '',
                'cc': '', 'cxx': '', 'ld': '', 'ar': '',
                'msvc_version': 'auto', 'target_arch': 'auto',
            },
        }

    def _call_lookup(self, cc_toolchain):
        return toolchain._lookup_config(self._section, cc_toolchain)

    def test_match_by_name_returns_config(self):
        cfg, kind = self._call_lookup('gcc-13')
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg['name'], 'gcc-13')
        self.assertEqual(kind, 'gcc')

    def test_match_by_kind_returns_kind_only(self):
        cfg, kind = self._call_lookup('clang')
        self.assertIsNone(cfg)
        self.assertEqual(kind, 'clang')

    def test_match_by_name_another(self):
        cfg, kind = self._call_lookup('clang-17')
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg['name'], 'clang-17')
        self.assertEqual(kind, 'clang')

    def test_unknown_name_warns_and_returns_empty(self):
        cfg, kind = self._call_lookup('nonexistent')
        self.assertIsNone(cfg)
        self.assertEqual(kind, '')

    def test_empty_cli_flag_returns_empty(self):
        cfg, kind = self._call_lookup('')
        self.assertIsNone(cfg)
        self.assertEqual(kind, '')


class ResolveConfigFallbackTest(unittest.TestCase):
    """Test _resolve_config with and without a named config dict."""

    def setUp(self):
        self._section = {
            '': {
                'kind': 'gcc',
                'target': 'linux',
                'prefix': '/default',
                'tool_prefix': '',
                'cc': '', 'cxx': '', 'ld': '', 'ar': '',
                'msvc_version': 'auto', 'target_arch': 'auto',
            },
        }

    def test_falls_back_to_section_when_cfg_is_none(self):
        (kind, target, prefix, tool_prefix, cc, cxx, ld, ar,
         target_arch, msvc_version) = toolchain._resolve_config(None, self._section)
        self.assertEqual(kind, 'gcc')
        self.assertEqual(target, 'linux')
        self.assertEqual(prefix, '/default')

    def test_named_config_overrides_section(self):
        named = {'kind': 'clang', 'target': 'darwin', 'prefix': '/opt/clang',
                 'tool_prefix': '', 'cc': '/opt/clang/bin/clang', 'cxx': '',
                 'ld': '', 'ar': '', 'msvc_version': 'auto', 'target_arch': 'auto'}
        (kind, target, prefix, tool_prefix, cc, cxx, ld, ar,
         target_arch, msvc_version) = toolchain._resolve_config(named, self._section)
        self.assertEqual(kind, 'clang')
        self.assertEqual(target, 'darwin')
        self.assertEqual(prefix, '/opt/clang')
        self.assertEqual(cc, '/opt/clang/bin/clang')


if __name__ == '__main__':
    unittest.main()
