#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for build variables (blade.set_variable / blade.get_variable).

Variables are the sanctioned bridge from the environment (or any config-time
computation) into otherwise-hermetic BUILD files: BLADE_ROOT declares them
(config phase only), BUILD files read them, `--define` overrides them, and the
resolved values fold into the config digest so a value change invalidates
cached builds.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402
from blade import dsl_api  # noqa: E402


class BuildVariableTest(unittest.TestCase):
    def setUp(self):
        # Fresh variable/define state on the config singleton for each test.
        config._blade_config._variables = {}
        config._blade_config._defines = {}
        self.cfg = dsl_api._BladeModule('blade', config_phase=True)
        self.build = dsl_api._BladeModule('blade', config_phase=False)

    def test_config_set_build_get(self):
        self.cfg.set_variable('use_x', '1')
        self.assertEqual(self.cfg.get_variable('use_x'), '1')
        self.assertEqual(self.build.get_variable('use_x'), '1')  # readable in BUILD

    def test_set_variable_is_config_phase_only(self):
        with self.assertRaises(SystemExit):
            self.build.set_variable('y', '1')  # console.fatal in BUILD phase

    def test_get_missing_with_default_ok_without_default_errors(self):
        self.assertEqual(self.build.get_variable('absent', 'fallback'), 'fallback')
        with mock.patch('blade.console.error') as err:
            self.assertIsNone(self.build.get_variable('absent'))
            self.assertTrue(err.called)  # undeclared read without default errors

    def test_duplicate_set_errors_unless_override(self):
        self.cfg.set_variable('v', 'a')
        with mock.patch('blade.console.error') as err:
            self.cfg.set_variable('v', 'b')  # no override -> error, value kept
            self.assertTrue(err.called)
        self.assertEqual(self.build.get_variable('v'), 'a')
        self.cfg.set_variable('v', 'b', override=True)
        self.assertEqual(self.build.get_variable('v'), 'b')

    def test_define_overrides_declared_value(self):
        self.cfg.set_variable('flag', '0')
        config.apply_defines(['flag=1'])
        self.assertEqual(self.build.get_variable('flag'), '1')  # CLI wins

    def test_validate_defines_rejects_undeclared(self):
        config.apply_defines(['undeclared=1'])
        with mock.patch('blade.console.error') as err:
            config.validate_defines()
            self.assertTrue(err.called)

    def test_apply_defines_rejects_bad_form(self):
        with mock.patch('blade.console.error') as err:
            config.apply_defines(['noequalsign'])
            self.assertTrue(err.called)

    def test_digest_tracks_variable_and_define_changes(self):
        self.cfg.set_variable('k', '1')
        d1 = config.digest()
        self.cfg.set_variable('k', '2', override=True)
        d2 = config.digest()
        self.assertNotEqual(d1, d2)  # value change invalidates the fingerprint
        config.apply_defines(['k=3'])
        self.assertNotEqual(d2, config.digest())  # --define change too


if __name__ == '__main__':
    unittest.main()
