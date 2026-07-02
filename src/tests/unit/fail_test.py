#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the `fail()` DSL builtin.

`fail(*args, sep=' ')` is the Starlark-compatible way to raise a hard error from
a BUILD / extension file (Starlark has no `assert` / `raise` / exceptions). It
reports a source-located error and aborts by raising SystemExit, which the
loader turns into a clean fatal (no Python traceback).
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import build_rules  # noqa: E402  (sys.path tweak above)
from blade import console  # noqa: E402
from blade import load_build_files  # noqa: E402


class FailTest(unittest.TestCase):
    def setUp(self):
        # Capture diagnostics rather than printing them.
        self._orig_diagnose = console.diagnose
        self.diagnostics = []
        console.diagnose = lambda loc, sev, msg: self.diagnostics.append((sev, msg))

    def tearDown(self):
        console.diagnose = self._orig_diagnose

    def test_aborts_with_system_exit(self):
        # SystemExit is the path the loader catches to emit a clean fatal.
        with self.assertRaises(SystemExit):
            load_build_files.fail('boom')

    def test_reports_an_error_diagnostic(self):
        with self.assertRaises(SystemExit):
            load_build_files.fail('bad thing')
        self.assertEqual([('error', 'bad thing')], self.diagnostics)

    def test_joins_positional_args_with_default_space(self):
        with self.assertRaises(SystemExit):
            load_build_files.fail('got', 2, 'files')
        self.assertEqual('got 2 files', self.diagnostics[0][1])

    def test_custom_separator(self):
        with self.assertRaises(SystemExit):
            load_build_files.fail('a', 'b', 'c', sep=', ')
        self.assertEqual('a, b, c', self.diagnostics[0][1])

    def test_registered_as_a_dsl_builtin(self):
        # Available to BUILD files (extensions inherit BUILD globals).
        self.assertIs(load_build_files.fail, build_rules.get_all().get('fail'))


if __name__ == '__main__':
    unittest.main()
