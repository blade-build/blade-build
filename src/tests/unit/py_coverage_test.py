#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for Python coverage support (#642).

Covers PyCoverageReporter: interpreter parsing and the no-op / degradation
paths (no data, coverage.py unavailable).
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import coverage  # noqa: E402


class PyCoverageReporterTest(unittest.TestCase):
    """Cover interpreter parsing and degradation."""

    def test_interpreter_is_split(self):
        # A multi-word interpreter (e.g. a coverage wrapper) is tokenized.
        r = coverage.PyCoverageReporter('bd', 'python3 -X dev')
        self.assertEqual(r._PyCoverageReporter__interp, ['python3', '-X', 'dev'])

    def test_noop_without_data(self):
        with tempfile.TemporaryDirectory() as d:
            r = coverage.PyCoverageReporter(d, 'python3')  # no py_coverage_data
            with mock.patch.object(coverage.subprocess, 'call') as call:
                r.generate()
                call.assert_not_called()

    def test_warns_when_coverage_unavailable(self):
        with tempfile.TemporaryDirectory() as d:
            data_dir = os.path.join(d, 'py_coverage_data')
            os.makedirs(data_dir)
            open(os.path.join(data_dir, '.coverage.host.1.x'), 'w').close()
            r = coverage.PyCoverageReporter(d, 'python3')
            # `coverage --version` fails -> unavailable; no combine/html attempted.
            with mock.patch.object(r, '_coverage', return_value=1) as cov:
                r.generate()
                # Only the version probe ran (one call), then it bailed out.
                self.assertEqual(cov.call_count, 1)
                self.assertEqual(cov.call_args[0][0], '--version')


if __name__ == '__main__':
    unittest.main()
