#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for LTO / ThinLTO flag dispatch and gating (#1378).

"""Tests the gcc/clang dispatch + gating of LTO.

LTO is a project intrinsic (`cc_config(lto='thin')`) overridable per invocation
(`--lto` / `--no-lto`), gated on the optimized profile (debug never gets LTO
unless `--lto` is explicit). The compile-side `-flto*` rides the overridable
`${lto}` ninja var (so a per-target lto=False blanks it); only the link flags
(the same flag plus the ThinLTO cache) are global. gcc has no ThinLTO -- its
parallel WHOPR (`-flto=auto`) maps to "thin"; MSVC is excluded in v1.
"""

import os
import sys
import tempfile
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_rule_support  # noqa: E402


def _tc(vendor='clang', target_os='linux', supports_cache=True):
    tc = mock.Mock()
    tc.target_os = target_os
    tc.cc = '/usr/bin/' + ('clang' if vendor == 'clang' else vendor)
    tc.cc_is = lambda v: v == vendor
    # The ThinLTO cache flag is linker-specific; default the probe to True
    # (lld/gold/ld64) so cache-bearing assertions hold, override for bfd.
    tc.supports_link_flag = lambda f: supports_cache
    return tc


def _opts(lto=None, profile='release'):
    o = mock.Mock()
    o.lto = lto
    o.profile = profile
    return o


def _mode(options, toolchain, cfg=''):
    """_lto_mode with cc_config.lto patched to ``cfg``."""
    with mock.patch.object(cc_rule_support.config, 'get_item', return_value=cfg):
        return cc_rule_support._lto_mode(options, toolchain)


class LtoModeTest(unittest.TestCase):
    """Resolution of the effective mode: CLI overrides, config policy, gating."""

    def test_config_policy_applies_in_release(self):
        self.assertEqual('thin', _mode(_opts(), _tc(), cfg='thin'))
        self.assertEqual('full', _mode(_opts(), _tc(), cfg='full'))

    def test_off_by_default(self):
        self.assertIsNone(_mode(_opts(), _tc(), cfg=''))

    def test_debug_never_gets_config_lto(self):
        self.assertIsNone(_mode(_opts(profile='debug'), _tc(), cfg='thin'))

    def test_cli_overrides_config(self):
        # --lto=no turns the project policy off.
        self.assertIsNone(_mode(_opts(lto='no'), _tc(), cfg='thin'))
        # --lto=full overrides a 'thin' policy.
        self.assertEqual('full', _mode(_opts(lto='full'), _tc(), cfg='thin'))

    def test_explicit_cli_forces_even_in_debug(self):
        # The escape hatch: --lto honored regardless of profile.
        self.assertEqual('thin', _mode(_opts(lto='thin', profile='debug'), _tc(), cfg=''))

    def test_msvc_excluded(self):
        self.assertIsNone(_mode(_opts(lto='thin'), _tc(vendor='msvc'), cfg='thin'))


class LtoCompileFlagTest(unittest.TestCase):
    """Per-toolchain spelling of the compile flag."""

    def test_clang(self):
        self.assertEqual('-flto=thin', cc_rule_support._lto_compile_flag('thin', _tc('clang')))
        self.assertEqual('-flto', cc_rule_support._lto_compile_flag('full', _tc('clang')))

    def test_gcc_thin_maps_to_auto(self):
        # gcc has no ThinLTO; -flto=auto is its parallel WHOPR equivalent.
        self.assertEqual('-flto=auto', cc_rule_support._lto_compile_flag('thin', _tc('gcc')))
        self.assertEqual('-flto', cc_rule_support._lto_compile_flag('full', _tc('gcc')))

    def test_none(self):
        # Returns '' (not None) when off, so callers need no `or ''`.
        self.assertEqual('', cc_rule_support._lto_compile_flag(None, _tc('clang')))


class LtoLinkFlagTest(unittest.TestCase):
    """Link flags: the compile flag + the ThinLTO cache (thin only)."""

    def test_thin_clang_linux_has_lld_cache(self):
        flags = cc_rule_support._lto_link_flags('thin', _tc('clang', 'linux'), '/bd')
        self.assertIn('-flto=thin', flags)
        self.assertIn('-Wl,--thinlto-cache-dir=/bd/.cache/thinlto', flags)

    def test_thin_clang_darwin_has_ld64_cache(self):
        flags = cc_rule_support._lto_link_flags('thin', _tc('clang', 'darwin'), '/bd')
        self.assertIn('-flto=thin', flags)
        self.assertIn('-Wl,-cache_path_lto,/bd/.cache/thinlto', flags)

    def test_gcc_has_no_thin_cache(self):
        flags = cc_rule_support._lto_link_flags('thin', _tc('gcc', 'linux'), '/bd')
        self.assertEqual(['-flto=auto'], flags)

    def test_full_has_no_cache(self):
        flags = cc_rule_support._lto_link_flags('full', _tc('clang', 'linux'), '/bd')
        self.assertEqual(['-flto'], flags)

    def test_bfd_linker_omits_unsupported_cache_flag(self):
        # GNU bfd rejects --thinlto-cache-dir: probe returns False -> the flag is
        # omitted (ThinLTO still works, just without the persistent cache).
        tc = _tc('clang', 'linux', supports_cache=False)
        flags = cc_rule_support._lto_link_flags('thin', tc, '/bd')
        self.assertEqual(['-flto=thin'], flags)


class LtoPluginToolTest(unittest.TestCase):
    """ar/nm routing: plugin tools on Linux, defaults (None) on macOS."""

    def test_macos_uses_default_tools(self):
        # Apple cctools ar/nm read bitcode natively -> no routing.
        self.assertEqual((None, None),
                         cc_rule_support._lto_plugin_ar_nm(_tc('clang', 'darwin')))

    def test_linux_gcc_resolves_gcc_ar_nm(self):
        with mock.patch('os.path.isfile', return_value=False), \
             mock.patch('shutil.which', side_effect=lambda n: '/usr/bin/' + n):
            ar, nm = cc_rule_support._lto_plugin_ar_nm(_tc('gcc', 'linux'))
        self.assertEqual('/usr/bin/gcc-ar', ar)
        self.assertEqual('/usr/bin/gcc-nm', nm)

    def test_linux_clang_resolves_llvm_ar_nm(self):
        with mock.patch('os.path.isfile', return_value=False), \
             mock.patch('shutil.which', side_effect=lambda n: '/usr/bin/' + n):
            ar, nm = cc_rule_support._lto_plugin_ar_nm(_tc('clang', 'linux'))
        self.assertEqual('/usr/bin/llvm-ar', ar)
        self.assertEqual('/usr/bin/llvm-nm', nm)

    def test_linux_missing_tools_returns_none(self):
        with mock.patch('os.path.isfile', return_value=False), \
             mock.patch('shutil.which', return_value=None):
            self.assertEqual((None, None),
                             cc_rule_support._lto_plugin_ar_nm(_tc('gcc', 'linux')))


class LtoIntrinsicFlagsTest(unittest.TestCase):
    """Through _get_intrinsic_cc_flags: link gets -flto when active, not the
    compile flag (that rides ${lto}), and nothing when off/debug."""

    def _link_flags(self, vendor='clang', target_os='linux', lto=None,
                    profile='release', cfg='thin'):
        gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
        gen.options = mock.Mock()
        gen.options.m = None
        gen.options.profile = profile
        gen.options.gprof = False
        gen.options.coverage = False
        gen.options.sanitizers = []
        gen.options.lto = lto
        setattr(gen.options, 'autofdo-generate', False)
        setattr(gen.options, 'autofdo-use', None)
        for a in ('profile-generate', 'profile-use'):
            try:
                delattr(gen.options, a)
            except AttributeError:
                pass
        gen.build_dir = tempfile.mkdtemp()
        gen.build_toolchain = _tc(vendor, target_os)
        gen.build_toolchain.filter_cc_flags = list
        gen.build_toolchain.supports_link_flag = lambda f: False
        section = {'fission': False, 'debug_info_levels': {'mid': ['-g']},
                   'no_semantic_interposition': False}
        gsection = {'debug_info_level': 'mid'}

        def fake_section(name):
            return {'cc_config': section, 'global_config': gsection}[name]

        with mock.patch.object(cc_rule_support.config, 'get_section',
                               side_effect=fake_section), \
             mock.patch.object(cc_rule_support.config, 'get_item', return_value=cfg):
            cppflags, linkflags = gen._get_intrinsic_cc_flags()
        return cppflags, linkflags

    def test_active_adds_link_flag_not_compile_flag(self):
        cppflags, linkflags = self._link_flags(cfg='thin')
        self.assertIn('-flto=thin', linkflags)
        # The compile flag rides ${lto}, so it must NOT be in the intrinsic
        # cppflags (else a per-target opt-out couldn't remove it).
        self.assertNotIn('-flto=thin', cppflags)

    def test_off_adds_nothing(self):
        _, linkflags = self._link_flags(cfg='')
        self.assertFalse([f for f in linkflags if 'flto' in f])

    def test_debug_adds_nothing(self):
        _, linkflags = self._link_flags(profile='debug', cfg='thin')
        self.assertFalse([f for f in linkflags if 'flto' in f])


class LtoBuildDirTest(unittest.TestCase):
    """LTO does NOT get its own build-dir variant (unlike PGO/coverage): the
    decision is stable and ships, so it rides the existing debug/release split
    + fingerprint-driven rebuild."""

    def _name(self, **opts):
        from blade.workspace import _build_dir_name

        class _TC:
            target_os = 'linux'
            target_arch = 'x86_64'

        class _Opts:
            profile = 'release'
            bits = '64'
            coverage = False
            sanitizers = None
            lto = None
            def __init__(self, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)
        return _build_dir_name('build_${profile}', _Opts(**opts), _TC())

    def test_lto_does_not_suffix_the_build_dir(self):
        self.assertEqual('build_release', self._name(lto='thin'))
        self.assertEqual('build_release', self._name(lto='full'))


if __name__ == '__main__':
    unittest.main()
