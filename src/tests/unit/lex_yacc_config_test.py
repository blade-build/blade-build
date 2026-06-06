#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors
# All rights reserved.
#
# Unit tests for lex_yacc_config — the config section that lets users override
# the flex / bison binaries (e.g. brew's keg-only bison 3.x on macOS).

"""Unit tests for lex_yacc_config and its consumer in backend.

The defaults and the BLADE_ROOT-facing ``lex_yacc_config(...)`` rule are the
contract we ship to users; the backend rule wiring is how that contract turns
into ninja commands. Tests below pin both ends so the chain doesn't quietly
silt over.
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402


class LexYaccConfigDefaultsTest(unittest.TestCase):
    """Pin the template defaults so the contract stays coherent."""

    def setUp(self):
        self._template = config._CONFIG_TEMPLATE['lex_yacc_config']

    def test_section_has_expected_keys(self):
        # The two binary paths are the entire public surface today; anything
        # else added later should land in this list deliberately, not by
        # accident.
        self.assertEqual(
            set(self._template.keys()) - {'__help__'},
            {'flex', 'bison'})

    def test_defaults_are_bare_names_on_posix(self):
        # On every non-Windows platform we ship the bare command name and let
        # PATH resolution take over — matches how Blade has always behaved.
        if os.name == 'nt':
            self.skipTest('posix-only default')
        self.assertEqual(self._template['flex'], 'flex')
        self.assertEqual(self._template['bison'], 'bison')

    def test_defaults_are_win_flex_bison_on_windows(self):
        # Windows defaults track the WinFlexBison project's names. The
        # `--wincompat` flag on win_flex is required for the generated
        # scanner to compile under MSVC.
        if os.name != 'nt':
            self.skipTest('windows-only default')
        self.assertEqual(self._template['flex'], 'win_flex --wincompat')
        self.assertEqual(self._template['bison'], 'win_bison')


class LexYaccConfigRuleTest(unittest.TestCase):
    """The ``lex_yacc_config(...)`` BLADE_ROOT rule must merge kwargs into the
    live config section."""

    def setUp(self):
        self._bc = config._blade_config
        self._saved_config = dict(self._bc.config)

    def tearDown(self):
        self._bc.config = self._saved_config

    def test_setting_bison_path_takes_effect(self):
        config.lex_yacc_config(bison='/opt/homebrew/opt/bison/bin/bison')
        section = self._bc.get_section('lex_yacc_config')
        assert section is not None  # get_section returns Optional; narrow for the checker
        self.assertEqual(
            section['bison'], '/opt/homebrew/opt/bison/bin/bison')
        # Other keys are not silently clobbered.
        self.assertIn('flex', section)

    def test_setting_both_at_once(self):
        config.lex_yacc_config(flex='/usr/local/bin/flex',
                               bison='/usr/local/bin/bison')
        section = self._bc.get_section('lex_yacc_config')
        assert section is not None
        self.assertEqual(section['flex'], '/usr/local/bin/flex')
        self.assertEqual(section['bison'], '/usr/local/bin/bison')


class _FakeRuleContext:
    """Minimal RuleContext stand-in for the lex_yacc rule provider.

    Captures emitted rules by name->command and serves the lex_yacc config
    section.
    """

    def __init__(self, lex_yacc_section):
        self._section = lex_yacc_section
        self.commands = {}

    def config_section(self, _name):
        return self._section

    def emit_rule(self, rule):
        self.commands[rule.name] = rule.command


class LexYaccBackendWiringTest(unittest.TestCase):
    """The lex_yacc rule provider (now in lex_yacc_target) must read from
    lex_yacc_config; users pinning a path via the BLADE_ROOT rule are entitled
    to see it surface in the ninja command line."""

    def _capture_rules(self, lex_yacc_section, fake_os_name='posix'):
        """Run the provider with mocked os.name, collect rule commands by name."""
        from blade import lex_yacc_target
        ctx = _FakeRuleContext(lex_yacc_section)
        with mock.patch('blade.lex_yacc_target.os.name', fake_os_name):
            lex_yacc_target._generate_lex_yacc_rules(ctx)
        return ctx.commands

    def test_posix_uses_config_values(self):
        cmds = self._capture_rules(
            {'flex': '/opt/homebrew/opt/flex/bin/flex',
             'bison': '/opt/homebrew/opt/bison/bin/bison'},
            fake_os_name='posix')
        # The override path must end up verbatim in the generated rule.
        self.assertIn('/opt/homebrew/opt/bison/bin/bison', cmds['yacc'])
        self.assertIn('/opt/homebrew/opt/flex/bin/flex', cmds['lex'])

    def test_windows_default_wraps_bison_pkgdatadir_when_unchanged(self):
        # When the user hasn't overridden bison, we keep the existing WinGet
        # data-dir sniff so win_bison can find m4sugar/.
        from blade import lex_yacc_target
        with mock.patch.object(
                lex_yacc_target, '_find_win_bison_data_dir',
                return_value=r'C:\Program Files\WinFlexBison\data'):
            cmds = self._capture_rules(
                {'flex': 'win_flex --wincompat', 'bison': 'win_bison'},
                fake_os_name='nt')
        # The data-dir sniff is applied, but only because bison == 'win_bison'.
        self.assertIn('BISON_PKGDATADIR=', cmds['yacc'])
        self.assertIn('win_bison', cmds['yacc'])

    def test_windows_custom_bison_skips_pkgdatadir_sniff(self):
        # If the user pinned a specific bison binary, the WinGet hack should
        # NOT muddy the command line — the user knows what they want.
        from blade import lex_yacc_target
        with mock.patch.object(
                lex_yacc_target, '_find_win_bison_data_dir',
                return_value=r'C:\Program Files\WinFlexBison\data'):
            cmds = self._capture_rules(
                {'flex': 'win_flex --wincompat',
                 'bison': r'C:\custom\bison.exe'},
                fake_os_name='nt')
        self.assertNotIn('BISON_PKGDATADIR=', cmds['yacc'])
        self.assertIn(r'C:\custom\bison.exe', cmds['yacc'])


if __name__ == '__main__':
    unittest.main()
