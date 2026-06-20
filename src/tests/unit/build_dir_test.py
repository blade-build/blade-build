#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for build-dir name composition (issue #1342).

`_build_dir_name` substitutes the platform triple (${os}/${arch}/${bits}) from
the selected toolchain into `global_config.build_path_template`, then appends the
sanitizer/coverage variant tag (never part of the template).
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.workspace import _build_dir_name  # noqa: E402


class _Opts:
    def __init__(self, profile='release', bits='64', coverage=False, sanitizers=None):
        self.profile = profile
        self.bits = bits
        self.coverage = coverage
        self.sanitizers = sanitizers


class _TC:
    def __init__(self, target_os='linux', target_arch='x86_64'):
        self.target_os = target_os
        self.target_arch = target_arch


class BuildDirNameTest(unittest.TestCase):
    def test_legacy_template_byte_for_byte(self):
        # The pinned legacy template reproduces the old name exactly.
        self.assertEqual(
            'build64_release',
            _build_dir_name('build${bits}_${profile}', _Opts(), _TC()))

    def test_flat_v3_default(self):
        self.assertEqual(
            'build_release',
            _build_dir_name('build_${profile}', _Opts(), _TC()))

    def test_shipped_default_template_is_flat(self):
        # The v3 default dropped the legacy `64`.
        from blade import config
        self.assertEqual(
            'build_${profile}',
            config._CONFIG_TEMPLATE['global_config']['build_path_template'])

    def test_os_arch_template(self):
        # os/arch come from the toolchain, not a flag.
        self.assertEqual(
            'build_darwin_arm64_release',
            _build_dir_name('build_${os}_${arch}_${profile}',
                            _Opts(), _TC('darwin', 'arm64')))

    def test_variants_appended_not_templated(self):
        # Sanitizer/coverage ride the trailing suffix regardless of template.
        self.assertEqual(
            'build_release_asan',
            _build_dir_name('build_${profile}',
                            _Opts(sanitizers=['address']), _TC()))
        self.assertEqual(
            'build64_release_coverage',
            _build_dir_name('build${bits}_${profile}',
                            _Opts(coverage=True), _TC()))
        # Composes on top of an os/arch template too.
        self.assertEqual(
            'build_linux_x86_64_release_coverage_asan',
            _build_dir_name('build_${os}_${arch}_${profile}',
                            _Opts(coverage=True, sanitizers=['address']), _TC()))

    def test_unknown_variable_is_fatal(self):
        with self.assertRaises(SystemExit):
            _build_dir_name('build_${bogus}_${profile}', _Opts(), _TC())


if __name__ == '__main__':
    unittest.main()
