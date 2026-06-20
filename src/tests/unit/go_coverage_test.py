#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for Go coverage support (#672).

Covers GoCoverageReporter: profile merging (one `mode:` header + all rows)
and the no-op/degradation paths.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import coverage  # noqa: E402


class GoMergeProfilesTest(unittest.TestCase):
    """`go tool cover` takes a single profile; we merge the per-test ones."""

    def _write(self, path, text):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def test_merge_keeps_one_mode_header_and_all_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = os.path.join(d, 'a.coverprofile')
            p2 = os.path.join(d, 'b.coverprofile')
            self._write(p1, 'mode: count\npkg/a.go:1.1,2.2 1 1\n')
            self._write(p2, 'mode: count\npkg/b.go:3.3,4.4 1 0\n')
            dest = os.path.join(d, 'merged')
            coverage.GoCoverageReporter.merge_profiles([p1, p2], dest)
            lines = open(dest, encoding='utf-8').read().splitlines()
            self.assertEqual(lines[0], 'mode: count')
            self.assertEqual(lines.count('mode: count'), 1)  # exactly one header
            self.assertIn('pkg/a.go:1.1,2.2 1 1', lines)
            self.assertIn('pkg/b.go:3.3,4.4 1 0', lines)


class GoCoverageReporterTest(unittest.TestCase):
    """Cover the degradation paths."""

    def test_noop_when_go_unconfigured(self):
        r = coverage.GoCoverageReporter('build64_release_coverage', '', '')
        with mock.patch.object(coverage.subprocess, 'call') as call:
            r.generate()
            call.assert_not_called()

    def test_noop_when_no_profiles(self):
        r = coverage.GoCoverageReporter('build64_release_coverage', 'go', '')
        with mock.patch.object(r, '_profiles', return_value=[]), \
                mock.patch.object(coverage.subprocess, 'call') as call:
            r.generate()
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
