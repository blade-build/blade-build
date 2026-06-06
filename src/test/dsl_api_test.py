# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>

"""Tests for the safe blade DSL API exposed to BLADE_ROOT / BUILD files."""

import os
import unittest

import blade_test  # noqa: F401  -- registers run() and adds blade to sys.path
from blade import console
from blade import dsl_api


class GetenvTest(unittest.TestCase):
    """blade.getenv: env-var lookup for env-driven config (config phase only)."""

    def setUp(self):
        self.blade = dsl_api.new_blade_module_for_config()
        self._saved_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._saved_env)

    def testReturnsValueWhenSet(self):
        os.environ['BLADE_TEST_GETENV'] = 'gcc-10'
        self.assertEqual(self.blade.getenv('BLADE_TEST_GETENV'), 'gcc-10')

    def testReturnsDefaultWhenUnset(self):
        os.environ.pop('BLADE_TEST_GETENV', None)
        self.assertEqual(self.blade.getenv('BLADE_TEST_GETENV', 'gcc'), 'gcc')

    def testReturnsNoneWhenUnsetWithoutDefault(self):
        os.environ.pop('BLADE_TEST_GETENV', None)
        self.assertIsNone(self.blade.getenv('BLADE_TEST_GETENV'))

    def testEmptyStringIsAValue(self):
        # An explicit empty value should win over the default --
        # matches os.environ.get semantics, which the user already knows.
        os.environ['BLADE_TEST_GETENV'] = ''
        self.assertEqual(self.blade.getenv('BLADE_TEST_GETENV', 'fallback'), '')

    def testFailsInBuildPhase(self):
        # _safe_blade_module(config_phase=False) gives the BUILD-phase shape
        # without requiring full workspace init.
        build_blade = dsl_api._safe_blade_module(config_phase=False)
        with self.assertRaises(SystemExit):
            build_blade.getenv('PATH')


if __name__ == '__main__':
    blade_test.run(GetenvTest)
