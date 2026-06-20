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


if __name__ == '__main__':
    unittest.main()
