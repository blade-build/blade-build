#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for C/C++ coverage support (#643).

Covers the variant build-dir suffix (so `--coverage` builds get their own
sibling dir without renaming the plain one) and the gcovr-based
CcCoverageReporter command construction + graceful degradation.
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import coverage  # noqa: E402
from blade.workspace import _build_variant_suffix  # noqa: E402


class _Opts:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class BuildVariantSuffixTest(unittest.TestCase):
    """The plain build keeps its historical name; variants self-prefix `_`."""

    def test_no_variant_is_empty(self):
        # Empty => build dir name unchanged (e.g. build64_release).
        self.assertEqual('', _build_variant_suffix(_Opts()))
        self.assertEqual('', _build_variant_suffix(_Opts(coverage=False)))

    def test_coverage_variant(self):
        self.assertEqual('_coverage', _build_variant_suffix(_Opts(coverage=True)))


class CcCoverageReporterTest(unittest.TestCase):
    """Cover the gcovr command builder and the no-op/degradation paths."""

    def _reporter(self, clang=False):
        return coverage.CcCoverageReporter('build64_release_coverage', '.', clang)

    def test_command_uses_root_and_html(self):
        cmd = self._reporter().build_gcovr_command('gcovr', 'report')
        self.assertEqual(cmd[0], 'gcovr')
        self.assertIn('--root', cmd)
        self.assertIn('build64_release_coverage', cmd)
        self.assertIn('--html-nested', cmd)

    def test_command_excludes_build_dir(self):
        # Generated sources (*.pb.cc) and vcpkg (installed under the build dir)
        # must be excluded so the report reflects the project's own code.
        cmd = self._reporter().build_gcovr_command('gcovr', 'report')
        self.assertIn('--exclude', cmd)
        self.assertIn('build64_release_coverage/', cmd)

    def test_command_tolerates_gcov_counter_glitches(self):
        # gcov's known counter overflow/underflow bug must not abort the report.
        cmd = self._reporter().build_gcovr_command('gcovr', 'report')
        self.assertIn('--gcov-ignore-parse-errors=all', cmd)

    def test_command_omits_gcov_executable_by_default(self):
        cmd = self._reporter().build_gcovr_command('gcovr', 'report')
        self.assertNotIn('--gcov-executable', cmd)

    def test_command_includes_gcov_executable_when_given(self):
        cmd = self._reporter().build_gcovr_command(
            'gcovr', 'report', 'xcrun llvm-cov gcov')
        self.assertIn('--gcov-executable', cmd)
        self.assertIn('xcrun llvm-cov gcov', cmd)

    def test_gcov_executable_gcc_is_default(self):
        self.assertIsNone(self._reporter(clang=False)._gcov_executable())

    def test_gcov_executable_clang_prefers_llvm_cov_on_path(self):
        with mock.patch.object(coverage.shutil, 'which',
                               side_effect=lambda p: '/usr/bin/llvm-cov'
                               if p == 'llvm-cov' else None):
            self.assertEqual('llvm-cov gcov',
                             self._reporter(clang=True)._gcov_executable())

    def test_gcov_executable_clang_falls_back_to_xcrun(self):
        # Apple toolchain: llvm-cov not on PATH, reachable via xcrun.
        with mock.patch.object(coverage.shutil, 'which',
                               side_effect=lambda p: '/usr/bin/xcrun'
                               if p == 'xcrun' else None):
            self.assertEqual('xcrun llvm-cov gcov',
                             self._reporter(clang=True)._gcov_executable())

    def test_generate_noop_without_coverage_data(self):
        r = self._reporter()
        with mock.patch.object(r, '_has_coverage_data', return_value=False), \
                mock.patch.object(coverage.subprocess, 'call') as call:
            r.generate()
            call.assert_not_called()

    def test_generate_warns_when_gcovr_missing(self):
        r = self._reporter()
        with mock.patch.object(r, '_has_coverage_data', return_value=True), \
                mock.patch.object(coverage.shutil, 'which', return_value=None), \
                mock.patch.object(coverage.subprocess, 'call') as call:
            r.generate()
            call.assert_not_called()


class MsvcCoverageReporterTest(unittest.TestCase):
    """Native cl.exe coverage: merge per-test Cobertura via the MS tool (#1369)."""

    _TOOL = r'C:\VS\Microsoft.CodeCoverage.Console.exe'

    def _reporter(self, collector=_TOOL):
        return coverage.MsvcCoverageReporter('build64_release_coverage', collector)

    def test_generate_noop_without_cobertura(self):
        r = self._reporter()
        with mock.patch.object(r, '_cobertura_files', return_value=[]), \
                mock.patch.object(coverage.os.path, 'isfile', return_value=False), \
                mock.patch.object(coverage.subprocess, 'call') as call:
            r.generate()
            call.assert_not_called()

    def test_generate_warns_when_collector_missing(self):
        # Per-test data exists but the tool was not found: warn, don't merge.
        r = self._reporter(collector='')
        with mock.patch.object(r, '_cobertura_files', return_value=['a.cobertura.xml']), \
                mock.patch.object(coverage.os.path, 'isfile', return_value=False), \
                mock.patch.object(coverage.subprocess, 'call') as call:
            r.generate()
            call.assert_not_called()

    def test_generate_merges_with_tool(self):
        r = self._reporter()
        files = ['x/a.cobertura.xml', 'y/b.cobertura.xml']
        with mock.patch.object(r, '_cobertura_files', return_value=files), \
                mock.patch.object(coverage.os.path, 'isfile', return_value=False), \
                mock.patch.object(coverage.os.path, 'exists', return_value=True), \
                mock.patch.object(coverage.subprocess, 'call', return_value=0) as call:
            r.generate()
        cmd = call.call_args[0][0]
        self.assertEqual(cmd[0], self._TOOL)
        self.assertIn('merge', cmd)
        self.assertIn('cobertura', cmd)
        # Output goes under cc_coverage_report; the inputs are appended.
        out = cmd[cmd.index('-o') + 1]
        self.assertTrue(out.endswith('coverage.cobertura.xml'))
        self.assertIn('cc_coverage_report', out)
        for f in files:
            self.assertIn(f, cmd)

    def test_generate_removes_stale_merged_first(self):
        # A prior merged file must be deleted before the walk so it is not
        # re-merged into itself.
        r = self._reporter()
        with mock.patch.object(r, '_cobertura_files', return_value=[]), \
                mock.patch.object(coverage.os.path, 'isfile', return_value=True), \
                mock.patch.object(coverage.os, 'remove') as rm:
            r.generate()
            rm.assert_called_once()


class GlobToRegexTest(unittest.TestCase):
    """coverage exclude globs -> regex with globstar semantics (#1369 follow-up)."""

    def _m(self, glob, path):
        import re
        return re.search(coverage._glob_to_regex(glob), path) is not None

    def test_dir_globstar_matches_subtree(self):
        self.assertTrue(self._m('thirdparty/**', 'a/thirdparty/x/y.cc'))
        self.assertTrue(self._m('thirdparty/**', r'C:\proj\thirdparty\x.h'))

    def test_leading_globstar_suffix(self):
        self.assertTrue(self._m('**/*_test.cc', 'a/b/foo_test.cc'))
        self.assertTrue(self._m('**/*_test.cc', 'foo_test.cc'))
        self.assertFalse(self._m('**/*_test.cc', 'a/foo_test.cpp'))

    def test_single_star_does_not_cross_separator(self):
        self.assertFalse(self._m('a/*.h', 'a/b/c.h'))
        self.assertTrue(self._m('a/*.h', 'a/c.h'))

    def test_dot_is_literal(self):
        # '.' must be escaped: '*.cc' should not match '_xcc'.
        self.assertFalse(self._m('*.cc', 'foo_xcc'))


class CoberturaRateTest(unittest.TestCase):
    def test_ratio(self):
        self.assertEqual('0.5', coverage._cobertura_rate(1, 2))

    def test_empty_is_one(self):
        self.assertEqual('1', coverage._cobertura_rate(0, 0))


class CcCoverageExcludeTest(unittest.TestCase):
    """gcovr gets a --exclude per configured glob, on top of the build-dir one."""

    def test_excludes_become_gcovr_filters(self):
        r = coverage.CcCoverageReporter('build64_release_coverage', '.', False,
                                        excludes=['thirdparty/**', '**/*_test.cc'])
        cmd = r.build_gcovr_command('gcovr', 'report')
        # Two user excludes plus the always-on build-dir exclude.
        self.assertEqual(3, cmd.count('--exclude'))
        joined = ' '.join(cmd)
        self.assertIn('thirdparty', joined)


_COBERTURA = '''<?xml version="1.0"?>
<coverage line-rate="0" lines-covered="0" lines-valid="0">
  <packages>
    <package name="p" line-rate="0">
      <classes>
        <class name="keep" filename="src/keep.cc">
          <lines>
            <line number="1" hits="1"/>
            <line number="2" hits="0"/>
          </lines>
        </class>
        <class name="drop" filename="thirdparty/dep.cc">
          <lines>
            <line number="1" hits="0"/>
            <line number="2" hits="0"/>
          </lines>
        </class>
      </classes>
    </package>
  </packages>
</coverage>'''


class MsvcCoverageExcludeTest(unittest.TestCase):
    """_apply_excludes drops matching classes and recomputes the Cobertura totals."""

    def _filtered_root(self, excludes):
        import tempfile
        import xml.etree.ElementTree as ET
        fd, path = tempfile.mkstemp(suffix='.cobertura.xml')
        os.close(fd)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(_COBERTURA)
        try:
            r = coverage.MsvcCoverageReporter('b', 'tool', excludes=excludes)
            r._apply_excludes(path)
            return ET.parse(path).getroot()
        finally:
            os.remove(path)

    def test_excluded_class_removed_and_totals_recomputed(self):
        root = self._filtered_root(['thirdparty/**'])
        names = [c.get('name') for c in root.iter('class')]
        self.assertEqual(['keep'], names)
        # Only keep.cc remains: 1 covered / 2 valid.
        self.assertEqual('1', root.get('lines-covered'))
        self.assertEqual('2', root.get('lines-valid'))
        self.assertEqual('0.5', root.get('line-rate'))

    def test_no_match_keeps_everything(self):
        root = self._filtered_root(['nomatch/**'])
        self.assertEqual(2, len(list(root.iter('class'))))
        # Both classes kept: 2 + 2 = 4 valid lines.
        self.assertEqual('4', root.get('lines-valid'))


if __name__ == '__main__':
    unittest.main()
