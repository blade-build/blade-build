#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for Target._check_deprecated_deps (#667).

The deprecated-dependency warning now lives on the base Target (so every
target type warns, not just cc) and is driven from before_generate(). These
tests pin the warning logic directly, bypassing target construction.
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.target import Target  # noqa: E402


class _Dep:
    """Minimal stand-in for a dependency target."""

    def __init__(self, fullname, deprecated, deps):
        self.fullname = fullname
        self.attr = {'deprecated': deprecated}
        self.deps = deps


class CheckDeprecatedDepsTest(unittest.TestCase):
    """Cover the base Target._check_deprecated_deps branches."""

    def _target(self, deps, database):
        target = Target.__new__(Target)  # bypass __init__
        target.deps = deps
        target.target_database = database
        target.warning = mock.Mock()
        return target

    def test_warns_on_deprecated_dep_with_replacement(self):
        dep = _Dep('//p:old', deprecated=True, deps=['p:new'])
        target = self._target(['p:old'], {'p:old': dep})
        target._check_deprecated_deps()
        target.warning.assert_called_once()
        msg = target.warning.call_args[0][0]
        self.assertIn('//p:old is deprecated', msg)
        self.assertIn('//p:new', msg)

    def test_no_warn_when_dep_not_deprecated(self):
        dep = _Dep('//p:ok', deprecated=False, deps=['p:x'])
        target = self._target(['p:ok'], {'p:ok': dep})
        target._check_deprecated_deps()
        target.warning.assert_not_called()

    def test_no_warn_when_deprecated_but_no_replacement(self):
        dep = _Dep('//p:old', deprecated=True, deps=[])
        target = self._target(['p:old'], {'p:old': dep})
        target._check_deprecated_deps()
        target.warning.assert_not_called()

    def test_unknown_dep_key_is_skipped(self):
        target = self._target(['p:gone'], {})
        target._check_deprecated_deps()
        target.warning.assert_not_called()


if __name__ == '__main__':
    unittest.main()
