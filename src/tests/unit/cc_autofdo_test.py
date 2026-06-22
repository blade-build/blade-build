#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for AutoFDO (sample-based PGO) flag dispatch (#1372).

"""Tests --autofdo-generate / --autofdo-use dispatch across gcc/clang/MSVC.

AutoFDO is sample-based PGO (no instrumentation):
  * generate: a normal optimized build + debug info -- clang adds
    `-fdebug-info-for-profiling -funique-internal-linkage-names`; gcc relies on
    the `-g` it already emits.
  * use: clang -> `-fprofile-sample-use=<profile>`, gcc -> `-fauto-profile=`.
    The profile must already be converted from perf.data (blade can't run the
    converter -- it needs the collected binary); a raw perf.data is rejected.
  * native MSVC -> SPGO (/GL + /spgo collect, /LTCG /spdin: optimize, the two
    compose for a steady-state build); clang-cl can't do either -> warned.
"""

import os
import sys
import tempfile
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402
from blade import cc_rule_support  # noqa: E402


def _make_generator(cc_vendor='gcc', target_os='linux',
                    autofdo_generate=False, autofdo_use=None):
    gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
    gen.options = mock.Mock()
    gen.options.m = None
    gen.options.profile = 'release'
    gen.options.gprof = False
    gen.options.coverage = False
    gen.options.sanitizers = []
    setattr(gen.options, 'autofdo-generate', autofdo_generate)
    setattr(gen.options, 'autofdo-use', autofdo_use)
    for attr in ('profile-generate', 'profile-use'):
        try:
            delattr(gen.options, attr)
        except AttributeError:
            pass
    gen.build_toolchain = mock.Mock()
    gen.build_toolchain.target_os = target_os
    gen.build_toolchain.cc = '/usr/bin/' + ('clang' if cc_vendor == 'clang' else cc_vendor)
    gen.build_toolchain.filter_cc_flags = lambda flags: list(flags)
    gen.build_toolchain.cc_is = lambda vendor: vendor == cc_vendor

    section = {'fission': False, 'debug_info_levels': {'mid': ['-g']},
               'no_semantic_interposition': False}
    global_section = {'debug_info_level': 'mid'}

    def fake_get_section(name):
        return {'cc_config': section, 'global_config': global_section}[name]

    return gen, fake_get_section


def _flags(gen, fake_get_section):
    with mock.patch.object(cc_rule_support.config, 'get_section',
                           side_effect=fake_get_section):
        return gen._get_intrinsic_cc_flags()


class AutofdoGenerateTest(unittest.TestCase):
    def test_clang_generate_adds_debug_info_flags(self):
        gen, fake = _make_generator(cc_vendor='clang', autofdo_generate=True)
        cppflags, _ = _flags(gen, fake)
        self.assertIn('-fdebug-info-for-profiling', cppflags)
        self.assertIn('-funique-internal-linkage-names', cppflags)

    def test_gcc_generate_no_clang_only_flags(self):
        # gcc rejects -fdebug-info-for-profiling / -funique-internal-linkage-names;
        # it relies on the -g blade already emits.
        gen, fake = _make_generator(cc_vendor='gcc', autofdo_generate=True)
        cppflags, _ = _flags(gen, fake)
        self.assertNotIn('-fdebug-info-for-profiling', cppflags)
        self.assertNotIn('-funique-internal-linkage-names', cppflags)

    def test_generate_off_adds_nothing(self):
        gen, fake = _make_generator(cc_vendor='clang', autofdo_generate=False)
        cppflags, _ = _flags(gen, fake)
        self.assertNotIn('-fdebug-info-for-profiling', cppflags)

    def test_autofdo_defines_no_pgo_macro(self):
        # AutoFDO samples a *normal* binary -- no instrumentation runtime to
        # flush -- so neither phase defines a PGO macro (keep it == production).
        prof = tempfile.NamedTemporaryFile(suffix='.prof', delete=False)
        prof.write(b'x')
        prof.close()
        self.addCleanup(os.unlink, prof.name)
        cases = [_make_generator(cc_vendor='clang', autofdo_generate=True),
                 _make_generator(cc_vendor='clang', autofdo_use=prof.name)]
        for gen, fake in cases:
            cppflags, _ = _flags(gen, fake)
            self.assertFalse([f for f in cppflags
                              if 'PGO_GENERATE' in f or 'PROFILE_GUIDED' in f])


class AutofdoUseTest(unittest.TestCase):
    def _profile_file(self, contents=b'not-perf-data'):
        f = tempfile.NamedTemporaryFile(suffix='.prof', delete=False)
        f.write(contents)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_clang_use_sample_profile(self):
        prof = self._profile_file()
        gen, fake = _make_generator(cc_vendor='clang', autofdo_use=prof)
        cppflags, _ = _flags(gen, fake)
        self.assertIn('-fprofile-sample-use=' + prof, cppflags)
        # AutoFDO is not instrumentation PGO -- no -fprofile-use / -fauto-profile.
        self.assertFalse([f for f in cppflags if f.startswith('-fprofile-use')])
        self.assertFalse([f for f in cppflags if f.startswith('-fauto-profile')])

    def test_gcc_use_auto_profile(self):
        prof = self._profile_file()
        gen, fake = _make_generator(cc_vendor='gcc', autofdo_use=prof)
        cppflags, _ = _flags(gen, fake)
        self.assertIn('-fauto-profile=' + prof, cppflags)
        self.assertFalse([f for f in cppflags if f.startswith('-fprofile-sample-use')])

    def test_raw_perf_data_is_rejected_with_warning(self):
        # A file with the PERFILE2 magic is a raw perf.data -> skip + warn.
        perf = self._profile_file(contents=b'PERFILE2\x00\x00')
        gen, fake = _make_generator(cc_vendor='clang', autofdo_use=perf)
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            cppflags, _ = _flags(gen, fake)
        self.assertFalse([f for f in cppflags if 'sample-use' in f])
        warn.assert_called_once()
        self.assertIn('perf.data', warn.call_args[0][0])

    def test_missing_profile_file_passes_path_through(self):
        # Non-existent path: can't read magic -> treated as a profile path
        # (compiler will surface its own error); blade doesn't guess.
        gen, fake = _make_generator(cc_vendor='clang', autofdo_use='/no/such.prof')
        cppflags, _ = _flags(gen, fake)
        self.assertIn('-fprofile-sample-use=/no/such.prof', cppflags)


class AutofdoBuildDirTest(unittest.TestCase):
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
            def __init__(self, **kw):
                for k, v in kw.items():
                    setattr(self, k, v)
        return _build_dir_name('build_${profile}', _Opts(**opts), _TC())

    def test_generate_and_use_share_autofdo_dir(self):
        self.assertEqual('build_release_autofdo',
                         self._name(**{'autofdo-generate': True}))
        self.assertEqual('build_release_autofdo',
                         self._name(**{'autofdo-use': '/tmp/x.prof'}))

    def test_normal_build_unsuffixed(self):
        self.assertEqual('build_release', self._name())


class AutofdoMsvcTest(unittest.TestCase):
    def setUp(self):
        cc_rule_support._autofdo_clang_cl_warned = False

    def test_active_predicate(self):
        self.assertTrue(cc_rule_support._autofdo_active(
            mock.Mock(**{'autofdo-generate': True, 'autofdo-use': None})))
        self.assertTrue(cc_rule_support._autofdo_active(
            mock.Mock(**{'autofdo-generate': False, 'autofdo-use': '/tmp/p'})))
        self.assertFalse(cc_rule_support._autofdo_active(
            mock.Mock(**{'autofdo-generate': False, 'autofdo-use': None})))

    def test_warn_clang_cl_fires_once(self):
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            cc_rule_support._warn_autofdo_clang_cl()
            cc_rule_support._warn_autofdo_clang_cl()
        warn.assert_called_once()
        self.assertIn('clang-cl', warn.call_args[0][0])


class SpgoMsvcTest(unittest.TestCase):
    """Native MSVC SPGO driven by --autofdo-* : /GL compile, /spgo collect,
    /LTCG /spdin: optimize, /LTCG lib."""

    def _opts(self, generate=False, use=None):
        opts = mock.Mock()
        setattr(opts, 'autofdo-generate', generate)
        setattr(opts, 'autofdo-use', use)
        return opts

    def test_compile_flags_gl_when_active(self):
        self.assertEqual(['/GL'], cc_rule_support._spgo_msvc_compile_flags(
            self._opts(generate=True)))
        self.assertEqual(['/GL'], cc_rule_support._spgo_msvc_compile_flags(
            self._opts(use='/tmp/app.spd')))
        self.assertEqual([], cc_rule_support._spgo_msvc_compile_flags(self._opts()))

    def test_lib_flags(self):
        self.assertEqual(['/LTCG'], cc_rule_support._spgo_msvc_lib_flags(
            self._opts(generate=True)))
        self.assertEqual([], cc_rule_support._spgo_msvc_lib_flags(self._opts()))

    def test_link_flags_collect_vs_optimize(self):
        self.assertEqual(['/spgo'], cc_rule_support._spgo_msvc_link_flags(
            self._opts(generate=True)))
        self.assertEqual(['/LTCG', '/spdin:/tmp/app.spd'],
                         cc_rule_support._spgo_msvc_link_flags(
                             self._opts(use='/tmp/app.spd')))
        self.assertEqual([], cc_rule_support._spgo_msvc_link_flags(self._opts()))

    def test_link_flags_combined_steady_state(self):
        # generate + use together -> one build that optimizes AND emits a fresh
        # .spd (verified legal on MSVC; /LTCG /spdin: + /spgo).
        self.assertEqual(['/LTCG', '/spdin:/tmp/app.spd', '/spgo'],
                         cc_rule_support._spgo_msvc_link_flags(
                             self._opts(generate=True, use='/tmp/app.spd')))

    def test_no_pgo_define(self):
        # SPGO samples a normal binary -- no flush define (like AutoFDO).
        self.assertFalse([f for f in cc_rule_support._spgo_msvc_compile_flags(
            self._opts(generate=True)) if 'PGO_GENERATE' in f or 'PROFILE_GUIDED' in f])


if __name__ == '__main__':
    unittest.main()
