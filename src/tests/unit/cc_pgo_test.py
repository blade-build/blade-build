#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for PGO (profile-guided optimization) flag dispatch (#1366).

"""Tests the gcc/clang/MSVC dispatch of --profile-generate / --profile-use.

PGO is a global build mode (#1366). The generate phase shares the
`-fprofile-generate` spelling on gcc and clang; the use phase diverges:

  * gcc: `-fprofile-use` reads `.gcda` directly + `-fprofile-correction`.
  * clang: rejects `-fprofile-correction`; needs a *merged* `.profdata`
    (blade merges `.profraw` via llvm-profdata) + clang mismatch suppressions.
  * native MSVC: a different flag family -- `/GL` on compile, `/LTCG /GENPROFILE`
    (instrument) or `/LTCG /USEPROFILE` (optimize, auto-merges the `.pgc`) on
    link, `/LTCG` on lib. Wired in the Windows rules, not the gcc/clang path.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402
from blade import cc_rule_support  # noqa: E402


def _make_generator(cc_vendor='gcc', target_os='linux',
                    profile_generate=None, profile_use=None):
    """A minimal CcRuleGenerator with the given PGO options and a toolchain
    that reports the requested vendor/os and returns flags verbatim."""
    gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
    gen.options = mock.Mock()
    gen.options.m = None
    gen.options.profile = 'release'
    gen.options.gprof = False
    gen.options.coverage = False
    gen.options.sanitizers = []
    setattr(gen.options, 'autofdo-generate', False)
    setattr(gen.options, 'autofdo-use', None)
    # PGO options use dashed dests; set/delete so getattr/hasattr behave like
    # argparse (absent attr => option not given).
    for attr, val in (('profile-generate', profile_generate),
                      ('profile-use', profile_use)):
        if val is None:
            try:
                delattr(gen.options, attr)
            except AttributeError:
                pass
        else:
            setattr(gen.options, attr, val)
    gen.build_toolchain = mock.Mock()
    gen.build_toolchain.target_os = target_os
    gen.build_toolchain.cc = '/usr/bin/' + ('clang' if cc_vendor == 'clang' else cc_vendor)
    gen.build_toolchain.filter_cc_flags = lambda flags: list(flags)
    gen.build_toolchain.cc_is = lambda vendor: vendor == cc_vendor

    section = {
        'fission': False,
        'debug_info_levels': {'mid': ['-g']},
        'no_semantic_interposition': False,
    }
    global_section = {'debug_info_level': 'mid'}

    def fake_get_section(name):
        return {'cc_config': section, 'global_config': global_section}[name]

    return gen, fake_get_section


def _flags(gen, fake_get_section):
    with mock.patch.object(cc_rule_support.config, 'get_section',
                           side_effect=fake_get_section):
        return gen._get_intrinsic_cc_flags()


class PgoGenerateTest(unittest.TestCase):
    """--profile-generate: same spelling on gcc/clang, both compile+link."""

    def test_gcc_generate_on_compile_and_link(self):
        gen, fake = _make_generator(cc_vendor='gcc', profile_generate='')
        cppflags, linkflags = _flags(gen, fake)
        self.assertIn('-fprofile-generate', cppflags)
        self.assertIn('-fprofile-generate', linkflags)

    def test_clang_generate_on_compile_and_link(self):
        gen, fake = _make_generator(cc_vendor='clang', target_os='darwin',
                                    profile_generate='')
        cppflags, linkflags = _flags(gen, fake)
        self.assertIn('-fprofile-generate', cppflags)
        self.assertIn('-fprofile-generate', linkflags)

    def test_generate_with_path(self):
        gen, fake = _make_generator(cc_vendor='gcc', profile_generate='/tmp/p')
        cppflags, linkflags = _flags(gen, fake)
        self.assertIn('-fprofile-generate=/tmp/p', cppflags)
        self.assertIn('-fprofile-generate=/tmp/p', linkflags)

    def test_generate_defines_blade_pgo_generate_only(self):
        # The instrument build defines BLADE_PGO_GENERATE (for profile flush);
        # the use build is a normal release and defines nothing.
        gen, fake = _make_generator(cc_vendor='clang', profile_generate='')
        cppflags, _ = _flags(gen, fake)
        self.assertIn('-DBLADE_PGO_GENERATE', cppflags)
        gen2, fake2 = _make_generator(cc_vendor='gcc', profile_use='/tmp/p')
        use_flags, _ = _flags(gen2, fake2)
        self.assertNotIn('-DBLADE_PGO_GENERATE', use_flags)
        self.assertFalse([f for f in use_flags if 'PROFILE_GUIDED' in f])

class PgoUseTest(unittest.TestCase):
    """--profile-use: gcc keeps -fprofile-correction; clang must not."""

    def test_gcc_use_has_correction(self):
        gen, fake = _make_generator(cc_vendor='gcc', profile_use='/tmp/prof')
        cppflags, _ = _flags(gen, fake)
        self.assertIn('-fprofile-use=/tmp/prof', cppflags)
        self.assertIn('-fprofile-correction', cppflags)
        self.assertIn('-Wno-error=coverage-mismatch', cppflags)

    def test_clang_use_drops_correction(self):
        # Point at a .profdata file so no merge subprocess runs.
        gen, fake = _make_generator(cc_vendor='clang', target_os='darwin',
                                    profile_use='/tmp/x.profdata')
        with mock.patch('os.path.isfile', return_value=True):
            cppflags, _ = _flags(gen, fake)
        self.assertIn('-fprofile-use=/tmp/x.profdata', cppflags)
        self.assertNotIn('-fprofile-correction', cppflags)
        # clang's own mismatch suppressions instead.
        self.assertIn('-Wno-error=profile-instr-out-of-date', cppflags)
        self.assertIn('-Wno-error=profile-instr-unprofiled', cppflags)

    def test_clang_use_merges_profraw_dir(self):
        """A directory of .profraw is merged once via llvm-profdata, and
        -fprofile-use points at the merged file."""
        cc_rule_support._clang_profdata_cache.clear()
        gen, fake = _make_generator(cc_vendor='clang', target_os='linux',
                                    profile_use='/tmp/pgodir')
        with mock.patch('os.path.isfile', return_value=False), \
             mock.patch('os.path.isdir', return_value=True), \
             mock.patch('glob.glob', return_value=['/tmp/pgodir/a.profraw']), \
             mock.patch.object(cc_rule_support, '_find_llvm_profdata',
                               return_value=['/usr/bin/llvm-profdata']), \
             mock.patch.object(cc_rule_support.util, 'run_command',
                               return_value=(0, '', '')) as run:
            cppflags, _ = _flags(gen, fake)
        merged = os.path.join('/tmp/pgodir', 'blade-merged.profdata')
        self.assertIn('-fprofile-use=' + merged, cppflags)
        self.assertNotIn('-fprofile-correction', cppflags)
        # The merge command was invoked.
        self.assertTrue(run.called)
        args = run.call_args[0][0]
        self.assertIn('merge', args)
        self.assertIn('/tmp/pgodir/a.profraw', args)

class PgoMsvcTest(unittest.TestCase):
    """Native MSVC PGO: /GL on compile, /LTCG + GEN/USEPROFILE on link, /LTCG on
    lib (#1366 Phase 2). The gcc/clang `-fprofile-*` path never runs for MSVC."""

    def _opts(self, generate=None, use=None):
        opts = mock.Mock()
        for attr, val in (('profile-generate', generate), ('profile-use', use)):
            if val is None:
                try:
                    delattr(opts, attr)
                except AttributeError:
                    pass
            else:
                setattr(opts, attr, val)
        return opts

    def test_compile_flags(self):
        # /GL under either mode (LTCG needs it); nothing when off.
        for mode in (dict(generate=''), dict(use='/tmp/p'), dict(generate='/tmp/p')):
            flags = cc_rule_support._pgo_msvc_compile_flags(self._opts(**mode))
            self.assertIn('/GL', flags)
        self.assertEqual([], cc_rule_support._pgo_msvc_compile_flags(self._opts()))

    def test_generate_define_only_on_instrument_build(self):
        # BLADE_PGO_GENERATE is for the instrument build (profile flush); the
        # optimize build behaves like a normal release and gets no PGO define.
        gen = cc_rule_support._pgo_msvc_compile_flags(self._opts(generate=''))
        self.assertIn('/DBLADE_PGO_GENERATE', gen)
        use = cc_rule_support._pgo_msvc_compile_flags(self._opts(use='/tmp/p'))
        self.assertNotIn('/DBLADE_PGO_GENERATE', use)
        self.assertFalse([f for f in use if 'PROFILE_GUIDED' in f])

    def test_lib_flags(self):
        self.assertEqual(['/LTCG'],
                         cc_rule_support._pgo_msvc_lib_flags(self._opts(generate='')))
        self.assertEqual(['/LTCG'],
                         cc_rule_support._pgo_msvc_lib_flags(self._opts(use='/p')))
        self.assertEqual([], cc_rule_support._pgo_msvc_lib_flags(self._opts()))

    def test_link_flags_dispatch(self):
        self.assertEqual(['/LTCG', '/GENPROFILE'],
                         cc_rule_support._pgo_msvc_link_flags(self._opts(generate='')))
        self.assertEqual(['/LTCG', '/USEPROFILE'],
                         cc_rule_support._pgo_msvc_link_flags(self._opts(use='/p')))
        self.assertEqual([], cc_rule_support._pgo_msvc_link_flags(self._opts()))


class PgoBuildDirTest(unittest.TestCase):
    """PGO builds get their own build dir, like coverage/asan."""

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

    def test_normal_build_unsuffixed(self):
        self.assertEqual('build_release', self._name())

    def test_generate_and_use_share_one_pgo_dir(self):
        # Both phases use `_pgo` so object paths match across them (gcc keys
        # its .gcda lookup by object path).
        self.assertEqual('build_release_pgo',
                         self._name(**{'profile-generate': ''}))
        self.assertEqual('build_release_pgo',
                         self._name(**{'profile-use': '/tmp/p'}))


if __name__ == '__main__':
    unittest.main()
