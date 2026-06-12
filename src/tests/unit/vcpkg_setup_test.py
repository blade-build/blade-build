#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for vcpkg orchestration: install_location + setup() (#1236, PR6).

"""Tests the Phase-2 orchestration logic with the vcpkg subprocess mocked.

install_location is pure. setup() writes the manifest / overlay triplet /
chainload into a tmpdir and invokes `vcpkg install`; the subprocess and the
tool lookup are patched, so these tests don't need a real vcpkg.
"""

import os
import sys
import tempfile
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import vcpkg  # noqa: E402


class InstallLocationTest(unittest.TestCase):

    def test_manage_uses_hermetic_tree_and_overlay(self):
        root, triplet = vcpkg.install_location(
            {'manage': True, 'install_dir': '.cache/vcpkg'}, 'x64-linux', 'build64')
        # Absolute (needed so the include dir survives _incs_to_fullpath).
        self.assertTrue(os.path.isabs(root))
        self.assertEqual(root, os.path.abspath(os.path.join('build64', '.cache/vcpkg')))
        self.assertEqual(triplet, 'blade-x64-linux')

    def test_unmanaged_uses_root_and_vanilla(self):
        root, triplet = vcpkg.install_location(
            {'manage': False, 'root': '/vc'}, 'x64-linux', 'build64')
        self.assertEqual(root, '/vc')
        self.assertEqual(triplet, 'x64-linux')

    def test_unmanaged_falls_back_to_env(self):
        with mock.patch.dict(os.environ, {'VCPKG_ROOT': '/envroot'}):
            root, _ = vcpkg.install_location(
                {'manage': False, 'root': ''}, 'x64-linux', 'b')
        self.assertEqual(root, '/envroot')


def _builder(build_dir):
    b = mock.Mock()
    b.get_build_dir.return_value = build_dir
    tc = b.get_build_toolchain.return_value
    tc.target_os, tc.target_arch = 'linux', 'x86_64'
    tc.cc_is = lambda v: v == 'gcc'
    tc.tool = lambda k: {'cc': '/usr/bin/gcc', 'cxx': '/usr/bin/g++'}.get(k)
    return b


_CFG = {
    'manage': True, 'packages': {'fmt': '10.2.1'}, 'install_dir': '.cache/vcpkg',
    'triplet': 'auto', 'baseline': '', 'registries': [], 'root': '',
}


class SetupTest(unittest.TestCase):

    def _run(self, build_dir, cfg=None, run_result=(0, 'ok', ''),
             tool: 'str | None' = '/vc/vcpkg'):
        cfg = dict(_CFG if cfg is None else cfg)
        with mock.patch('blade.config.get_section', return_value=cfg), \
             mock.patch('blade.vcpkg._find_vcpkg_tool', return_value=tool), \
             mock.patch('blade.console.info'), \
             mock.patch('blade.console.error'), \
             mock.patch('blade.util.run_command', return_value=run_result) as rc:
            ok = vcpkg.setup(_builder(build_dir))
        return ok, rc

    def test_manage_false_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            ok, rc = self._run(d, cfg=dict(_CFG, manage=False))
        self.assertTrue(ok)
        rc.assert_not_called()

    def test_no_packages_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            ok, rc = self._run(d, cfg=dict(_CFG, packages={}))
        self.assertTrue(ok)
        rc.assert_not_called()

    def test_generates_files_and_invokes_install(self):
        with tempfile.TemporaryDirectory() as d:
            ok, rc = self._run(d)
            self.assertTrue(ok)
            base = os.path.join(d, '.cache/vcpkg')
            self.assertTrue(os.path.exists(os.path.join(base, 'vcpkg.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'blade-chainload.cmake')))
            self.assertTrue(os.path.exists(
                os.path.join(base, 'triplets', 'blade-x64-linux.cmake')))
            self.assertTrue(os.path.exists(os.path.join(base, '.blade-vcpkg-stamp')))
        cmd = rc.call_args[0][0]
        self.assertIn('install', cmd)
        self.assertIn('blade-x64-linux', cmd)
        self.assertIn('--x-install-root', cmd)

    def test_install_failure_returns_false(self):
        with tempfile.TemporaryDirectory() as d:
            ok, _ = self._run(d, run_result=(1, '', 'boom'))
        self.assertFalse(ok)

    def test_tool_not_found_returns_false(self):
        with tempfile.TemporaryDirectory() as d:
            ok, rc = self._run(d, tool=None)
        self.assertFalse(ok)
        rc.assert_not_called()

    def test_stamp_skips_reinstall(self):
        with tempfile.TemporaryDirectory() as d:
            # First run installs and writes the stamp.
            ok1, rc1 = self._run(d)
            self.assertTrue(ok1)
            rc1.assert_called_once()
            # Simulate vcpkg having created the install root.
            os.makedirs(os.path.join(d, '.cache/vcpkg', 'installed'), exist_ok=True)
            # Second run with identical inputs must skip the subprocess.
            ok2, rc2 = self._run(d)
            self.assertTrue(ok2)
            rc2.assert_not_called()


if __name__ == '__main__':
    unittest.main()
