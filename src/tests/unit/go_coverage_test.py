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


class GoModuleGroupingTest(unittest.TestCase):
    """`go tool cover -html` must run inside the owning module (#1369 follow-up):
    the workspace root has no go.mod, so a root run can't resolve import paths."""

    def test_read_module_path(self):
        with tempfile.TemporaryDirectory() as d:
            gomod = os.path.join(d, 'go.mod')
            with open(gomod, 'w', encoding='utf-8') as f:
                f.write('module blade.test/gobasic\n\ngo 1.22\n')
            self.assertEqual('blade.test/gobasic',
                             coverage.GoCoverageReporter._read_module_path(gomod))

    def test_group_single_module(self):
        modules = {'blade.test/gobasic': 'suites/go_basic'}
        rows = ['blade.test/gobasic/greeter/greeter.go:1.1,2.2 1 1',
                'blade.test/gobasic/hello/main.go:3.3,4.4 1 0']
        groups = coverage.GoCoverageReporter._group_by_module(rows, modules)
        self.assertEqual({'suites/go_basic': rows}, groups)

    def test_group_longest_prefix_wins(self):
        # A nested module must not be swallowed by its parent's prefix.
        modules = {'blade.test/a': 'a', 'blade.test/a/b': 'a/b'}
        rows = ['blade.test/a/x.go:1.1,2.2 1 1',
                'blade.test/a/b/y.go:1.1,2.2 1 1']
        groups = coverage.GoCoverageReporter._group_by_module(rows, modules)
        self.assertEqual(['blade.test/a/x.go:1.1,2.2 1 1'], groups['a'])
        self.assertEqual(['blade.test/a/b/y.go:1.1,2.2 1 1'], groups['a/b'])

    def test_group_unmatched_row_dropped(self):
        groups = coverage.GoCoverageReporter._group_by_module(
            ['other.com/x/y.go:1.1,2.2 1 1'], {'blade.test/a': 'a'})
        self.assertEqual({}, groups)

    def _reporter_over(self, rows, modules):
        """Run generate() with a merged profile of `rows` and given modules,
        capturing the `go tool cover` commands (subprocess mocked)."""
        r = coverage.GoCoverageReporter(tempfile.mkdtemp(), 'go', '')
        merged_text = 'mode: count\n' + '\n'.join(rows) + '\n'
        with mock.patch.object(r, '_profiles', return_value=['dummy']), \
                mock.patch.object(r, 'merge_profiles') as merge, \
                mock.patch.object(r, '_discover_modules', return_value=modules), \
                mock.patch.object(coverage.subprocess, 'call',
                                  return_value=0) as call:
            # merge_profiles is stubbed; write the merged file it would produce.
            merge.side_effect = lambda profiles, dest: open(
                dest, 'w', encoding='utf-8').write(merged_text)
            r.generate()
        return [c.args[0] for c in call.call_args_list]

    def test_generate_runs_cover_in_module_dir(self):
        cmds = self._reporter_over(
            ['blade.test/gobasic/greeter/greeter.go:1.1,2.2 1 1'],
            {'blade.test/gobasic': 'suites/go_basic'})
        self.assertEqual(1, len(cmds))
        cmd = cmds[0]
        self.assertIn('-C', cmd)
        self.assertEqual('suites/go_basic', cmd[cmd.index('-C') + 1])
        self.assertTrue(any(a.endswith('index.html') for a in cmd))

    def test_generate_multi_module_renders_each(self):
        cmds = self._reporter_over(
            ['blade.test/a/x.go:1.1,2.2 1 1', 'blade.test/b/y.go:1.1,2.2 1 1'],
            {'blade.test/a': 'a', 'blade.test/b': 'b'})
        dirs = {cmd[cmd.index('-C') + 1] for cmd in cmds}
        self.assertEqual({'a', 'b'}, dirs)
        # Multi-module => no single index.html; each is a distinct cover_*.html.
        self.assertFalse(any(a.endswith('index.html') for cmd in cmds for a in cmd))

    def test_generate_warns_when_no_module_matches(self):
        r = coverage.GoCoverageReporter(tempfile.mkdtemp(), 'go', '')
        with mock.patch.object(r, '_profiles', return_value=['dummy']), \
                mock.patch.object(r, 'merge_profiles',
                                  side_effect=lambda p, dest: open(
                                      dest, 'w', encoding='utf-8').write(
                                          'mode: count\nother.com/x.go:1.1,2.2 1 1\n')), \
                mock.patch.object(r, '_discover_modules', return_value={}), \
                mock.patch.object(coverage.subprocess, 'call') as call:
            r.generate()
            call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
