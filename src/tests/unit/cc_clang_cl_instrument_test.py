#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for clang-cl instrumentation routing (coverage / PGO), #1369.

"""clang-cl keeps cl-style flags (so cc_is('msvc') and the Windows rules apply),
but for instrumentation it takes the LLVM mechanism, not cl.exe's /GL+/LTCG.
The is_clang_cl() predicate routes it:

  * coverage -> gcov-style ``--coverage`` (compile + the profile runtime on
    /LIBPATH at link, since lld-link gets no driver flags);
  * PGO -> ``-fprofile-generate`` / ``-fprofile-use=<merged.profdata>``.

clang-cl is not on the CI box, so this is flag-routing + best-effort link
validation (see the helpers' docstrings).
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_rule_support  # noqa: E402


def _opts(coverage=False, generate=None, use=None):
    """An options Mock with coverage + dashed PGO dests behaving like argparse
    (absent attr => option not given)."""
    opts = mock.Mock()
    opts.coverage = coverage
    for attr, val in (('profile-generate', generate), ('profile-use', use)):
        if val is None:
            try:
                delattr(opts, attr)
            except AttributeError:
                pass
        else:
            setattr(opts, attr, val)
    return opts


class ClangClCompileFlagsTest(unittest.TestCase):
    """_instrument_clang_cl_compile_flags: LLVM compile-side instrumentation."""

    def _flags(self, **kw):
        return cc_rule_support._instrument_clang_cl_compile_flags(
            mock.Mock(), _opts(**kw))

    def test_off_is_empty(self):
        self.assertEqual([], self._flags())

    def test_coverage_adds_gcov_flag(self):
        self.assertIn('--coverage', self._flags(coverage=True))

    def test_pgo_generate(self):
        flags = self._flags(generate='')
        self.assertIn('-fprofile-generate', flags)
        # Instrument build only -- lets source flush the profile runtime.
        self.assertIn('-DBLADE_PGO_GENERATE', flags)

    def test_pgo_generate_with_path(self):
        self.assertIn('-fprofile-generate=/tmp/p', self._flags(generate='/tmp/p'))

    def test_pgo_use_resolves_profdata_and_suppresses(self):
        with mock.patch.object(cc_rule_support, '_resolve_clang_profdata',
                               return_value='/m.profdata'):
            flags = cc_rule_support._instrument_clang_cl_compile_flags(
                mock.Mock(), _opts(use='/tmp/raw'))
        self.assertIn('-fprofile-use=/m.profdata', flags)
        self.assertIn('-Wno-error=profile-instr-out-of-date', flags)
        # The optimize build is a normal release -- no PGO define.
        self.assertNotIn('-DBLADE_PGO_GENERATE', flags)
        self.assertFalse([f for f in flags if 'PROFILE_GUIDED' in f])
        self.assertIn('-Wno-error=profile-instr-unprofiled', flags)
        # clang's gcc-style -fprofile-correction must NOT appear.
        self.assertNotIn('-fprofile-correction', flags)

    def test_coverage_and_pgo_compose(self):
        flags = self._flags(coverage=True, generate='')
        self.assertIn('--coverage', flags)
        self.assertIn('-fprofile-generate', flags)


class ClangClLinkFlagsTest(unittest.TestCase):
    """_instrument_clang_cl_link_flags: profile runtime on /LIBPATH for lld-link."""

    def _tc(self, libdir):
        tc = mock.Mock()
        tc.profile_runtime_libdir.return_value = libdir
        return tc

    def test_off_is_empty(self):
        self.assertEqual(
            [], cc_rule_support._instrument_clang_cl_link_flags(
                self._tc('C:/rt'), _opts()))

    def test_coverage_adds_libpath(self):
        flags = cc_rule_support._instrument_clang_cl_link_flags(
            self._tc('C:/rt'), _opts(coverage=True))
        self.assertEqual(['/LIBPATH:C:/rt'], flags)

    def test_generate_adds_libpath(self):
        flags = cc_rule_support._instrument_clang_cl_link_flags(
            self._tc('C:/rt'), _opts(generate=''))
        self.assertEqual(['/LIBPATH:C:/rt'], flags)

    def test_libpath_quoted_when_spaced(self):
        flags = cc_rule_support._instrument_clang_cl_link_flags(
            self._tc(r'C:\Program Files\rt'), _opts(coverage=True))
        self.assertEqual([r'/LIBPATH:"C:\Program Files\rt"'], flags)

    def test_use_needs_no_runtime(self):
        # --profile-use reads the profile at compile time; nothing at link.
        self.assertEqual(
            [], cc_rule_support._instrument_clang_cl_link_flags(
                self._tc('C:/rt'), _opts(use='/m.profdata')))

    def test_missing_runtime_warns_once(self):
        cc_rule_support._clang_cl_profile_runtime_warned = False
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            flags = cc_rule_support._instrument_clang_cl_link_flags(
                self._tc(''), _opts(coverage=True))
            cc_rule_support._instrument_clang_cl_link_flags(
                self._tc(''), _opts(coverage=True))
        self.assertEqual([], flags)
        warn.assert_called_once()


def _windows_gen(is_clang_cl, coverage=False, generate=None, use=None,
                 libdir='C:/rt'):
    """A CcRuleGenerator wired for the Windows rules with a clang-cl-or-not
    toolchain, to exercise the dispatch (not just the helpers)."""
    gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
    gen.build_toolchain = mock.Mock()
    gen.build_toolchain.is_clang_cl.return_value = is_clang_cl
    gen.build_toolchain.profile_runtime_libdir.return_value = libdir
    gen.build_toolchain.filter_cc_flags = lambda f, *a: list(f)
    gen.build_toolchain.get_system_include_paths.return_value = []
    gen.build_toolchain.get_system_lib_paths.return_value = []
    gen.build_toolchain.tool = lambda k: None
    gen.build_accelerator = mock.Mock()
    gen.build_accelerator.get_cc_commands.return_value = ('cl', 'cl', 'lld-link')
    gen.build_accelerator.get_ar_command.return_value = 'llvm-lib'
    gen.options = _opts(coverage=coverage, generate=generate, use=use)
    gen.options.profile = 'release'
    gen.options.sanitizers = []
    gen.build_dir = 'build64_release_coverage'
    gen._msvc_tee_wrapper_py = mock.Mock(return_value='cc_wrapper.py')
    gen._msvc_link_wrapper_py = mock.Mock(return_value='lw.py')
    gen._builtin_command = lambda b, args='': 'cmd'
    gen.generate_rule = mock.Mock()
    captured = []
    gen._add_line = captured.append
    gen._captured = captured
    return gen


_SECTION = {
    'msvc_config': {'cppflags': [], 'cflags': [], 'cxxflags': [],
                    'optimize': {'release': ['/O2']},
                    'debug_info_levels': {'mid': ['/Z7']}, 'linkflags': [],
                    'warnings': []},
    'cc_config': {'cflags': [], 'cxxflags': [], 'cppflags': [], 'extra_incs': [],
                  'linkflags': []},
    'cc_library_config': {'deterministic': False, 'thin': False},
    'global_config': {'debug_info_level': 'mid'},
}


class ClangClWindowsRuleDispatchTest(unittest.TestCase):
    """The Windows rules route clang-cl to LLVM instrumentation, cl.exe to LTCG."""

    def _run(self, method, gen):
        with mock.patch('blade.cc_rule_support.config') as cfg:
            cfg.get_section.side_effect = lambda n: _SECTION[n]
            method(gen)

    def _compile_cc(self, gen):
        self._run(lambda g: g._generate_windows_cc_compile_rules('cl', 'cl'), gen)
        return {c.kwargs['name']: c.kwargs['command']
                for c in gen.generate_rule.call_args_list}['cc']

    def test_clang_cl_coverage_compile_has_gcov_flag(self):
        cc = self._compile_cc(_windows_gen(True, coverage=True))
        self.assertIn('--coverage', cc)

    def test_cl_exe_coverage_compile_has_no_flag(self):
        # Native cl.exe collects coverage at run time, not via a compile flag.
        cc = self._compile_cc(_windows_gen(False, coverage=True))
        self.assertNotIn('--coverage', cc)

    def test_clang_cl_pgo_generate_compile_uses_llvm_not_gl(self):
        cc = self._compile_cc(_windows_gen(True, generate=''))
        self.assertIn('-fprofile-generate', cc)
        self.assertNotIn('/GL', cc)

    def test_cl_exe_pgo_generate_compile_uses_gl(self):
        cc = self._compile_cc(_windows_gen(False, generate=''))
        self.assertIn('/GL', cc)
        self.assertNotIn('-fprofile-generate', cc)

    def test_clang_cl_ar_skips_ltcg(self):
        gen = _windows_gen(True, generate='')
        self._run(lambda g: g._generate_windows_ar_rules(), gen)
        cmd = gen.generate_rule.call_args[1]['command']
        self.assertNotIn('/LTCG', cmd)

    def test_clang_cl_link_adds_runtime_libpath(self):
        gen = _windows_gen(True, coverage=True)
        self._run(lambda g: g._generate_windows_link_rules(), gen)
        linkline = next(s for s in gen._captured if s.startswith('linkflags'))
        self.assertIn('/LIBPATH:C:/rt', linkline)
        self.assertNotIn('/GENPROFILE', linkline)

    def test_cl_exe_link_uses_ltcg_genprofile(self):
        gen = _windows_gen(False, generate='')
        self._run(lambda g: g._generate_windows_link_rules(), gen)
        linkline = next(s for s in gen._captured if s.startswith('linkflags'))
        self.assertIn('/GENPROFILE', linkline)
        self.assertIn('/LTCG', linkline)


if __name__ == '__main__':
    unittest.main()
