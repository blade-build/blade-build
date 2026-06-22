#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for the instrumentation-flag platform gating in
# _get_intrinsic_cc_flags (--gprof and --coverage).

"""Tests that instrumentation flags are only emitted where they work.

  * ``--gprof`` -> ``-pg`` is only functional on Linux (gcc/clang). Darwin
    clang accepts ``-pg`` but ignores it (spraying
    ``-Wunused-command-line-argument`` per compile, no ``gmon.out``); MSVC does
    not understand it. Non-Linux targets skip the dead flag and warn once.

  * ``--coverage`` is the gcc/clang driver flag, emitted here for gcc and
    clang. MSVC toolchains (cl.exe *and* clang-cl) are cc_is('msvc') and never
    reach _get_intrinsic_cc_flags -- they take the Windows rules. There cl.exe
    collects coverage at run time (Microsoft.CodeCoverage.Console.exe) and
    clang-cl emits LLVM instrumentation from the Windows rules; that routing is
    covered by cc_clang_cl_instrument_test. See issue #1369.

The gprof warning fires once per build (the guard is module-level), not once
per target, so a many-target build does not get spammed.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402
from blade import cc_rule_support  # noqa: E402


def _make_generator(target_os, cc_vendor='gcc', gprof=False, coverage=False):
    """A minimal CcRuleGenerator with the given instrumentation options, a
    toolchain that reports the requested target_os/vendor and returns flags
    verbatim, and the few `options` attrs `_get_intrinsic_cc_flags` reads."""
    gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
    gen.options = mock.Mock()
    gen.options.m = None
    gen.options.profile = 'release'
    gen.options.gprof = gprof
    gen.options.coverage = coverage
    gen.options.sanitizers = []
    setattr(gen.options, 'autofdo-generate', False)
    setattr(gen.options, 'autofdo-use', None)
    for attr in ('profile-generate', 'profile-use'):
        try:
            delattr(gen.options, attr)
        except AttributeError:
            pass
    gen.build_toolchain = mock.Mock()
    gen.build_toolchain.target_os = target_os
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


class CcGprofGatingTest(unittest.TestCase):
    """`--gprof` adds `-pg` only on Linux; warns once elsewhere."""

    def setUp(self):
        cc_rule_support._gprof_unsupported_warned = False

    def test_linux_adds_pg_to_compile_and_link(self):
        """On Linux gprof is real: `-pg` rides both cppflags and linkflags."""
        gen, fake = _make_generator('linux', gprof=True)
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            cppflags, linkflags = _flags(gen, fake)
        self.assertIn('-pg', cppflags)
        self.assertIn('-pg', linkflags)
        warn.assert_not_called()

    def test_linux_clang_also_adds_pg(self):
        """gprof is gated on the *platform*, not the vendor: clang on Linux
        supports `-pg` (mcount) just like gcc, so it must NOT be excluded."""
        gen, fake = _make_generator('linux', cc_vendor='clang', gprof=True)
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            cppflags, linkflags = _flags(gen, fake)
        self.assertIn('-pg', cppflags)
        self.assertIn('-pg', linkflags)
        warn.assert_not_called()

    def test_darwin_skips_pg_and_warns_once(self):
        """On macOS `-pg` is a no-op; skip it and warn (once)."""
        gen, fake = _make_generator('darwin', cc_vendor='clang', gprof=True)
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            cppflags, linkflags = _flags(gen, fake)
            # A second target's flag computation must not re-warn.
            gen2, fake2 = _make_generator('darwin', cc_vendor='clang', gprof=True)
            _flags(gen2, fake2)
        self.assertNotIn('-pg', cppflags)
        self.assertNotIn('-pg', linkflags)
        warn.assert_called_once()
        self.assertIn('gprof', warn.call_args[0][0])
        self.assertIn('darwin', warn.call_args[0][0])

    def test_msvc_skips_pg_and_warns(self):
        """MSVC does not understand `-pg`; skip it and warn."""
        gen, fake = _make_generator('windows', cc_vendor='msvc', gprof=True)
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            cppflags, linkflags = _flags(gen, fake)
        self.assertNotIn('-pg', cppflags)
        self.assertNotIn('-pg', linkflags)
        warn.assert_called_once()

    def test_gprof_off_is_silent_everywhere(self):
        """No gprof => no flag and no warning regardless of platform."""
        gen, fake = _make_generator('darwin', cc_vendor='clang', gprof=False)
        with mock.patch.object(cc_rule_support.console, 'warning') as warn:
            cppflags, linkflags = _flags(gen, fake)
        self.assertNotIn('-pg', cppflags)
        self.assertNotIn('-pg', linkflags)
        warn.assert_not_called()


class CcCoverageGatingTest(unittest.TestCase):
    """`--coverage` rides the gcc/clang path. MSVC toolchains never reach here
    (cc_is('msvc') -> Windows rules); their routing is tested elsewhere."""

    def test_gcc_adds_coverage_to_compile_and_link(self):
        """gcc gets the driver flag on both sides."""
        gen, fake = _make_generator('linux', cc_vendor='gcc', coverage=True)
        cppflags, linkflags = _flags(gen, fake)
        self.assertIn('--coverage', cppflags)
        self.assertIn('--coverage', linkflags)

    def test_clang_adds_coverage_to_compile_and_link(self):
        """clang shares the gcc-style --coverage spelling."""
        gen, fake = _make_generator('linux', cc_vendor='clang', coverage=True)
        cppflags, linkflags = _flags(gen, fake)
        self.assertIn('--coverage', cppflags)
        self.assertIn('--coverage', linkflags)

    def test_coverage_off_is_silent(self):
        """No coverage => no flag."""
        gen, fake = _make_generator('linux', cc_vendor='gcc', coverage=False)
        cppflags, linkflags = _flags(gen, fake)
        self.assertNotIn('--coverage', cppflags)
        self.assertNotIn('--coverage', linkflags)


if __name__ == '__main__':
    unittest.main()
