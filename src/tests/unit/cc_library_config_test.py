#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for cc_library_config template defaults, validation,
# and platform-aware archive command generation.

"""Unit tests for cc_library_config."""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402


class CcLibraryConfigDefaultsTest(unittest.TestCase):
    """Pin the template defaults so the contract stays coherent."""

    def setUp(self):
        self._template = config._CONFIG_TEMPLATE['cc_library_config']

    def test_default_deterministic_is_false(self):
        self.assertFalse(self._template['deterministic'])

    def test_default_thin_is_false(self):
        self.assertFalse(self._template['thin'])

    def test_arflags_still_exists_for_backward_compat(self):
        self.assertIn('arflags', self._template)
        self.assertEqual(self._template['arflags'], ['rcs'])

    def test_ranlibflags_removed(self):
        self.assertNotIn('ranlibflags', self._template)

    def test_generate_dynamic_still_exists(self):
        self.assertIn('generate_dynamic', self._template)
        self.assertFalse(self._template['generate_dynamic'])


class CcLibraryConfigValidationTest(unittest.TestCase):
    """Test the validation/deprecation logic in cc_library_config()."""

    def setUp(self):
        self._bc = config._blade_config
        # Save config dict so we can restore it after each test.
        self._saved_config = dict(self._bc.config)

    def tearDown(self):
        self._bc.config = self._saved_config

    def _call(self, **kwargs):
        """Call cc_library_config and capture warning/error messages."""
        warnings = []
        errors = []
        with mock.patch.object(self._bc, 'warning', side_effect=warnings.append), \
             mock.patch.object(self._bc, 'error', side_effect=errors.append):
            config.cc_library_config(**kwargs)
        return warnings, errors

    def test_deterministic_bool_accepted_without_warning(self):
        warnings, errors = self._call(deterministic=True)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])

    def test_thin_bool_accepted_without_warning(self):
        warnings, errors = self._call(thin=True)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])

    def test_arflags_alone_emits_warning(self):
        warnings, errors = self._call(arflags=['rcsD'])
        self.assertEqual(len(warnings), 1)
        self.assertIn('deprecated', warnings[0])
        self.assertEqual(errors, [])

    def test_arflags_with_deterministic_errors(self):
        warnings, errors = self._call(arflags=['rcsD'], deterministic=True)
        self.assertEqual(len(errors), 1)
        self.assertIn('cannot be used together', errors[0])
        self.assertEqual(warnings, [])

    def test_arflags_with_thin_errors(self):
        warnings, errors = self._call(arflags=['rcsT'], thin=True)
        self.assertEqual(len(errors), 1)
        self.assertIn('cannot be used together', errors[0])
        self.assertEqual(warnings, [])

    def test_no_conflict_without_arflags(self):
        warnings, errors = self._call(deterministic=True, thin=True)
        self.assertEqual(warnings, [])
        self.assertEqual(errors, [])


class CcArchiveRulesTest(unittest.TestCase):
    """Test platform-specific archive command generation."""

    def _make_gen(self, target_os):
        """Build a CcRuleGenerator with enough state for ar tests.

        The cc ar rules moved to cc_rule_support.CcRuleGenerator (M2 of #1264);
        config/console are module globals there.
        """
        from blade import cc_rule_support
        gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
        gen._add_line = mock.Mock()
        gen.build_toolchain = mock.Mock()
        gen.build_toolchain.target_os = target_os
        gen.build_accelerator = mock.Mock()
        gen.build_accelerator.get_ar_command.return_value = 'ar'
        return gen

    def _capture_ar_command(self, gen, deterministic=False, thin=False):
        """Call _generate_cc_ar_rules and return the generated command."""
        with mock.patch.object(gen, 'generate_rule') as mock_rule:
            with mock.patch('blade.cc_rule_support.config') as mock_config:
                mock_config.get_section.return_value = {
                    'arflags': ['rcs'],
                    'deterministic': deterministic,
                    'thin': thin,
                }
                gen._generate_cc_ar_rules()
                self.assertTrue(mock_rule.called, 'generate_rule was not called')
                return mock_rule.call_args[1]['command']

    def _capture_windows_ar_command(self, gen, deterministic=False, thin=False):
        """Call _generate_windows_ar_rules and return the generated command."""
        with mock.patch.object(gen, 'generate_rule') as mock_rule:
            with mock.patch('blade.cc_rule_support.config') as mock_config:
                mock_config.get_section.return_value = {
                    'deterministic': deterministic,
                    'thin': thin,
                }
                gen._generate_windows_ar_rules()
                self.assertTrue(mock_rule.called, 'generate_rule was not called')
                return mock_rule.call_args[1]['command']

    # --- Linux ---

    def test_linux_default(self):
        gen = self._make_gen('linux')
        cmd = self._capture_ar_command(gen, deterministic=False, thin=False)
        self.assertIn('ar rcs ', cmd)

    def test_linux_deterministic(self):
        gen = self._make_gen('linux')
        cmd = self._capture_ar_command(gen, deterministic=True, thin=False)
        self.assertIn('ar rcsD ', cmd)

    def test_linux_thin(self):
        gen = self._make_gen('linux')
        cmd = self._capture_ar_command(gen, deterministic=False, thin=True)
        self.assertIn('ar rcsT ', cmd)

    def test_linux_deterministic_and_thin(self):
        gen = self._make_gen('linux')
        cmd = self._capture_ar_command(gen, deterministic=True, thin=True)
        self.assertIn('ar rcsDT ', cmd)

    # --- macOS ---

    def test_darwin_default(self):
        gen = self._make_gen('darwin')
        cmd = self._capture_ar_command(gen, deterministic=False, thin=False)
        self.assertIn('ar rcs ', cmd)

    def test_darwin_deterministic_uses_libtool(self):
        gen = self._make_gen('darwin')
        cmd = self._capture_ar_command(gen, deterministic=True, thin=False)
        self.assertIn('libtool -static -no_warning_for_no_symbols -o $out $in', cmd)

    def test_darwin_thin_logs_error(self):
        gen = self._make_gen('darwin')
        with mock.patch.object(gen, 'generate_rule'):
            with mock.patch('blade.cc_rule_support.console') as mock_console:
                with mock.patch('blade.cc_rule_support.config') as mock_config:
                    mock_config.get_section.return_value = {
                        'arflags': ['rcs'],
                        'deterministic': False,
                        'thin': True,
                    }
                    gen._generate_cc_ar_rules()
                    mock_console.error.assert_called_once()
                    self.assertIn('thin', mock_console.error.call_args[0][0])

    # --- Windows (MSVC) ---

    def test_windows_default(self):
        gen = self._make_gen('windows')
        cmd = self._capture_windows_ar_command(gen, deterministic=False, thin=False)
        self.assertIn('/nologo ', cmd)
        self.assertNotIn('/Brepro', cmd)

    def test_windows_deterministic(self):
        gen = self._make_gen('windows')
        cmd = self._capture_windows_ar_command(gen, deterministic=True, thin=False)
        self.assertIn('/nologo /Brepro', cmd)

    def test_windows_thin_warns(self):
        gen = self._make_gen('windows')
        with mock.patch.object(gen, 'generate_rule'):
            with mock.patch('blade.cc_rule_support.console') as mock_console:
                with mock.patch('blade.cc_rule_support.config') as mock_config:
                    mock_config.get_section.return_value = {
                        'deterministic': False,
                        'thin': True,
                    }
                    gen._generate_windows_ar_rules()
                    mock_console.warning.assert_called_once()
                    self.assertIn('thin', mock_console.warning.call_args[0][0])

    # --- Unknown platform ---

    def test_unknown_platform_falls_back_to_arflags(self):
        gen = self._make_gen('freebsd')
        cmd = self._capture_ar_command(gen, deterministic=True, thin=True)
        self.assertIn('ar rcs ', cmd)
        self.assertNotIn('D', cmd)
        self.assertNotIn('T', cmd)


if __name__ == '__main__':
    unittest.main()
