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


class LexYaccBackendWiringTest(unittest.TestCase):
    """The backend rule generation must read from lex_yacc_config; users
    pinning a path via the BLADE_ROOT rule are entitled to see it surface in
    the ninja command line."""

    def _make_gen(self, target_os='posix'):
        """Build a _NinjaFileHeaderGenerator with just enough state for the
        lex/yacc rule generator to run.

        Mirrors the helper used by cc_library_config_test.CcArchiveRulesTest.
        """
        from blade import backend
        gen = backend._NinjaFileHeaderGenerator.__new__(
            backend._NinjaFileHeaderGenerator)
        gen._NinjaFileHeaderGenerator__all_rule_names = set()
        gen.rules_buf = []
        gen._add_line = mock.Mock()
        return gen

    def _capture_rules(self, gen, lex_yacc_section, fake_os_name='posix'):
        """Run generate_lex_yacc_rules with mocked config + os, collect the
        generated rule commands by name."""
        from blade import backend
        commands = {}

        def fake_generate_rule(name, command, description):
            commands[name] = command

        with mock.patch.object(gen, 'generate_rule',
                               side_effect=fake_generate_rule), \
             mock.patch('blade.backend.config') as mock_config, \
             mock.patch('blade.backend.os.name', fake_os_name):
            mock_config.get_section.return_value = lex_yacc_section
            gen.generate_lex_yacc_rules()
        return commands

    def test_posix_uses_config_values(self):
        gen = self._make_gen()
        cmds = self._capture_rules(
            gen,
            {'flex': '/opt/homebrew/opt/flex/bin/flex',
             'bison': '/opt/homebrew/opt/bison/bin/bison'},
            fake_os_name='posix')
        # The override path must end up verbatim in the generated rule.
        self.assertIn('/opt/homebrew/opt/bison/bin/bison', cmds['yacc'])
        self.assertIn('/opt/homebrew/opt/flex/bin/flex', cmds['lex'])

    def test_windows_default_wraps_bison_pkgdatadir_when_unchanged(self):
        # When the user hasn't overridden bison, we keep the existing WinGet
        # data-dir sniff so win_bison can find m4sugar/.
        gen = self._make_gen()
        from blade import backend
        with mock.patch.object(
                backend._NinjaFileHeaderGenerator,
                '_find_win_bison_data_dir',
                return_value=r'C:\Program Files\WinFlexBison\data'):
            cmds = self._capture_rules(
                gen,
                {'flex': 'win_flex --wincompat', 'bison': 'win_bison'},
                fake_os_name='nt')
        # The data-dir sniff is applied, but only because bison == 'win_bison'.
        self.assertIn('BISON_PKGDATADIR=', cmds['yacc'])
        self.assertIn('win_bison', cmds['yacc'])

    def test_windows_custom_bison_skips_pkgdatadir_sniff(self):
        # If the user pinned a specific bison binary, the WinGet hack should
        # NOT muddy the command line — the user knows what they want.
        gen = self._make_gen()
        from blade import backend
        with mock.patch.object(
                backend._NinjaFileHeaderGenerator,
                '_find_win_bison_data_dir',
                return_value=r'C:\Program Files\WinFlexBison\data'):
            cmds = self._capture_rules(
                gen,
                {'flex': 'win_flex --wincompat',
                 'bison': r'C:\custom\bison.exe'},
                fake_os_name='nt')
        self.assertNotIn('BISON_PKGDATADIR=', cmds['yacc'])
        self.assertIn(r'C:\custom\bison.exe', cmds['yacc'])


if __name__ == '__main__':
    unittest.main()
