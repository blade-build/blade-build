#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for cc_binary / cc_plugin strip_options (#694)."""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402


def _target(strip_options):
    # strip_options is stored normalized (var_to_list) on the attr.
    t = cc_targets.CcBinary.__new__(cc_targets.CcBinary)
    t.attr = {'strip_options': strip_options}
    return t


class StripCommandOptionsTest(unittest.TestCase):
    def test_default_is_strip_unneeded(self):
        # Unset -> the historical default (safe for shared objects).
        self.assertEqual('--strip-unneeded', _target([])._strip_command_options())

    def test_custom_single(self):
        self.assertEqual('--strip-all', _target(['--strip-all'])._strip_command_options())

    def test_custom_multiple_joined(self):
        self.assertEqual(
            '--strip-debug -K keep_me',
            _target(['--strip-debug', '-K', 'keep_me'])._strip_command_options())


if __name__ == '__main__':
    unittest.main()
