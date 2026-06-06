#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for cc_config.pie and cc_config.no_semantic_interposition.

"""Tests the PIE / semantic-interposition knobs added for issue #1258.

Covers three pieces:

  * Template defaults (`'auto'` / `True`) so the contract stays coherent.
  * `cc_config()` validation: `pie` only accepts ``'auto' | 'yes' | 'no'``.
  * `_get_intrinsic_cc_flags` honors `no_semantic_interposition`
    (default True = pass ``-fno-semantic-interposition`` on GCC only;
    Clang/Apple Clang would warn-as-error on the C++ driver).

The link-rule plumbing (target_os == 'linux' -> `${pie_flag}` only on the
binary `link` rule, never on `solink`) is exercised indirectly here by
unit-testing the surrounding state -- a full ninja-rule emit test would
need the whole `BuildManager` stood up. The wiring is tiny and the
behavior is observable via `blade build` integration.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402
from blade import cc_rule_support  # noqa: E402


class CcConfigPieDefaultsTest(unittest.TestCase):
    """Pin the template defaults so opt-in stays opt-in."""

    def setUp(self):
        self._template = config._CONFIG_TEMPLATE['cc_config']

    def test_pie_defaults_to_auto(self):
        """Default `'auto'` preserves today's "whatever the toolchain
        defaults to" posture. Anything else would silently change every
        existing user's binaries."""
        self.assertEqual(self._template['pie'], 'auto')

    def test_no_semantic_interposition_defaults_to_true(self):
        """Default True = pass ``-fno-semantic-interposition`` (on GCC), so
        users on -fPIC get back most of the -fPIE-level perf -- own globals
        don't go through the GOT, cross-TU inlining of them is allowed.
        Affects only app-internal symbols (LD_PRELOAD'd malloc/jemalloc target
        libc symbols and are unaffected); users with plugin frameworks that
        rely on overriding exe-internal symbols set this to False to opt out.
        Naming follows GCC's own flag and CPython's
        ``Py_HAVE_NO_SEMANTIC_INTERPOSITION`` -- the double negative reads
        naturally because the GCC flag itself is ``-fno-...``.
        """
        self.assertTrue(self._template['no_semantic_interposition'])

    def test_help_text_present(self):
        """Both knobs must carry help text for `blade dump --config`."""
        self.assertIn('pie__help__', self._template)
        self.assertIn('no_semantic_interposition__help__', self._template)


class CcConfigPieValidationTest(unittest.TestCase):
    """`pie` is a tri-state string; anything else must error at config time."""

    def setUp(self):
        self._bc = config._blade_config
        self._saved = dict(self._bc.config)

    def tearDown(self):
        self._bc.config = self._saved

    def _call(self, **kwargs):
        warnings, errors = [], []
        with mock.patch.object(self._bc, 'warning', side_effect=warnings.append), \
             mock.patch.object(self._bc, 'error', side_effect=errors.append):
            config.cc_config(**kwargs)
        return warnings, errors

    def test_pie_auto_accepted(self):
        _, errors = self._call(pie='auto')
        self.assertEqual(errors, [])

    def test_pie_yes_accepted(self):
        _, errors = self._call(pie='yes')
        self.assertEqual(errors, [])

    def test_pie_no_accepted(self):
        _, errors = self._call(pie='no')
        self.assertEqual(errors, [])

    def test_pie_invalid_string_errors(self):
        """A typo like ``pie='true'`` is the most likely user mistake and
        must be caught at config-load time, not silently treated as auto."""
        _, errors = self._call(pie='true')
        self.assertEqual(len(errors), 1)
        self.assertIn('pie', errors[0])

    def test_pie_bool_errors(self):
        """``pie=True`` looks plausible from a casual reader but the knob
        is intentionally tri-state (auto means "leave it to the toolchain",
        which a bool can't express). Reject so the user picks one of the
        three real values. Two errors fire here -- the enum check + the
        config-store type check -- both with the right verdict, so we only
        assert at least one."""
        _, errors = self._call(pie=True)
        self.assertGreaterEqual(len(errors), 1)
        self.assertTrue(any('pie' in e for e in errors))

    def test_no_semantic_interposition_bool_accepted(self):
        """The interposition knob is a plain bool; no enum validation."""
        _, errors = self._call(no_semantic_interposition=True)
        self.assertEqual(errors, [])


class GetIntrinsicCcFlagsInterpositionTest(unittest.TestCase):
    """`_get_intrinsic_cc_flags` appends ``-fno-semantic-interposition`` iff
    `cc_config.no_semantic_interposition` is True (the default) AND the
    detected cc vendor is real GCC. Setting it False opts out, restoring
    GCC's conservative interposable-globals behavior. The Clang skip is
    structural (Clang's C++ driver fires -Wunused-command-line-argument for
    this flag, which -Werror projects can't accept); ``filter_cc_flags``
    can't catch it because it probes in C, where Clang stays silent.
    """

    def _make_generator(self, no_semantic_interposition, cc_vendor='gcc'):
        """Build a minimal _NinjaFileHeaderGenerator with the cc_config
        items the method reads, a mocked toolchain that returns flags
        verbatim and reports the requested cc vendor, and the few
        `options` attrs the method touches.
        """
        # Avoid running NinjaFileHeaderGenerator.__init__ (which wants a
        # BuildManager, options, build dirs etc.). Construct an empty
        # object and only set the fields the method actually reads.
        gen = cc_rule_support.CcRuleGenerator.__new__(
            cc_rule_support.CcRuleGenerator)
        gen.options = mock.Mock()
        # _get_intrinsic_cc_flags reads .m, .profile, and three pgo-ish
        # `getattr(self.options, 'name', default)` calls. We set sentinels
        # so none of the conditional branches add extra flags that would
        # confuse the assertions.
        gen.options.m = None
        gen.options.profile = 'release'
        gen.options.gprof = False
        gen.options.coverage = False
        # `hasattr(self.options, '...')` on a Mock returns True by default;
        # explicitly delete the attrs so the PGO branches stay out.
        for attr in ('profile-generate', 'profile-use'):
            try:
                delattr(gen.options, attr)
            except AttributeError:
                pass
        gen.build_toolchain = mock.Mock()
        gen.build_toolchain.filter_cc_flags = lambda flags: list(flags)
        gen.build_toolchain.cc_is = lambda vendor: vendor == cc_vendor

        # Stub config: only the keys actually read need to be present.
        section = {
            'fission': False,
            'debug_info_levels': {'mid': ['-g']},
            'no_semantic_interposition': no_semantic_interposition,
        }
        global_section = {'debug_info_level': 'mid'}

        def fake_get_section(name):
            return {'cc_config': section, 'global_config': global_section}[name]

        return gen, fake_get_section

    def test_default_true_adds_flag_on_gcc(self):
        """Default ``no_semantic_interposition=True`` on real GCC adds the
        ``-fno-semantic-interposition`` flag -- the perf-win posture this
        knob exists to enable."""
        gen, fake_get_section = self._make_generator(True, cc_vendor='gcc')
        with mock.patch.object(cc_rule_support.config, 'get_section', side_effect=fake_get_section):
            cppflags, _ = gen._get_intrinsic_cc_flags()
        self.assertIn('-fno-semantic-interposition', cppflags)

    def test_opt_out_omits_flag(self):
        """Setting False reverts to GCC's interposable default by omitting
        the flag. Used by plugin/in-app hook frameworks that rely on
        overriding exe-internal symbols."""
        gen, fake_get_section = self._make_generator(False, cc_vendor='gcc')
        with mock.patch.object(cc_rule_support.config, 'get_section', side_effect=fake_get_section):
            cppflags, _ = gen._get_intrinsic_cc_flags()
        self.assertNotIn('-fno-semantic-interposition', cppflags)

    def test_flag_skipped_on_clang_even_at_default(self):
        """Clang (incl. Apple Clang) is already non-interposing by default
        AND fires ``-Wunused-command-line-argument`` for the flag on its C++
        driver, which ``-Werror`` projects can't accept. So we never emit
        the flag on Clang -- same posture Clang gives natively, no warning
        noise."""
        gen, fake_get_section = self._make_generator(True, cc_vendor='clang')
        with mock.patch.object(cc_rule_support.config, 'get_section', side_effect=fake_get_section):
            cppflags, _ = gen._get_intrinsic_cc_flags()
        self.assertNotIn('-fno-semantic-interposition', cppflags)


if __name__ == '__main__':
    unittest.main()
