#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for vcpkg reference resolution + the dep-scheme handler (#1236, PR4).

"""Tests resolve_reference (pure), triplet_for_toolchain, and the
`vcpkg#...` provider handler.

The handler's only side effects are constructing a VcpkgLibrary and calling
referrer.blade.register_target(); VcpkgLibrary itself needs a live BuildManager,
so it is patched out here -- its construction is exercised by the build-level
tests. The resolution *logic* (whitelist, path computation, error messages) is
fully covered by the pure resolve_reference tests.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import vcpkg  # noqa: E402


_WHITELIST = {'fmt': '10.2.1', 'openssl': {'version': '3.2.1'}, 'nlohmann-json': '3.11.3'}


class ResolveReferenceTest(unittest.TestCase):

    def _resolve(self, coord, packages=None, root='/vc', triplet='x64-linux'):
        return vcpkg.resolve_reference(
            coord, _WHITELIST if packages is None else packages, root, triplet)

    def test_valid_reference(self):
        info = self._resolve('fmt:fmt')
        self.assertEqual(info['port'], 'fmt')
        self.assertEqual(info['lib'], 'fmt')
        self.assertEqual(info['key'], 'vcpkg#fmt:fmt')
        self.assertFalse(info['header_only'])
        self.assertEqual(info['lib_dir'], '/vc/installed/x64-linux/lib')
        self.assertEqual(info['include_dir'], '/vc/installed/x64-linux/include')

    def test_msvc_debug_links_debug_lib_subtree(self):
        # An MSVC-ABI debug build links debug/lib (ABI-incompatible CRT/STL),
        # but the include dir is shared (headers ship with the release install).
        info = vcpkg.resolve_reference('fmt:fmt', _WHITELIST, '/vc',
                                       'x64-windows', profile='debug')
        self.assertEqual(info['lib_dir'],
                         os.path.join('/vc', 'installed', 'x64-windows', 'debug', 'lib'))
        self.assertEqual(info['include_dir'],
                         os.path.join('/vc', 'installed', 'x64-windows', 'include'))

    def test_non_msvc_debug_still_links_release_lib(self):
        # clang/gcc/MinGW debug builds reuse the release tree.
        for triplet in ('x64-linux', 'x64-mingw-dynamic'):
            info = vcpkg.resolve_reference('fmt:fmt', _WHITELIST, '/vc',
                                           triplet, profile='debug')
            self.assertEqual(info['lib_dir'],
                             os.path.join('/vc', 'installed', triplet, 'lib'))

    def test_lib_basename_differs_from_port(self):
        info = self._resolve('openssl:ssl')
        self.assertEqual(info['key'], 'vcpkg#openssl:ssl')
        self.assertEqual(info['lib'], 'ssl')

    def test_header_only_sentinel(self):
        info = self._resolve('nlohmann-json:hdrs')
        self.assertTrue(info['header_only'])

    def test_missing_colon_rejected(self):
        with self.assertRaises(vcpkg.VcpkgError) as cm:
            self._resolve('fmt')
        self.assertIn('must name a library', str(cm.exception))

    def test_empty_lib_rejected(self):
        with self.assertRaises(vcpkg.VcpkgError):
            self._resolve('fmt:')

    def test_non_whitelisted_port_is_hard_error(self):
        with self.assertRaises(vcpkg.VcpkgError) as cm:
            self._resolve('boost:boost')
        msg = str(cm.exception)
        self.assertIn('whitelist', msg)
        self.assertIn('boost', msg)

    def test_no_root_rejected(self):
        with self.assertRaises(vcpkg.VcpkgError) as cm:
            self._resolve('fmt:fmt', root='')
        self.assertIn('install root', str(cm.exception))

    def test_no_triplet_rejected(self):
        with self.assertRaises(vcpkg.VcpkgError) as cm:
            self._resolve('fmt:fmt', triplet='')
        self.assertIn('triplet', str(cm.exception))


class TripletForToolchainTest(unittest.TestCase):

    def _tc(self, target_os, arch, vendor):
        tc = mock.Mock()
        tc.target_os = target_os
        tc.target_arch = arch
        tc.cc_is = lambda v: v == vendor
        return tc

    def test_gcc_linux(self):
        self.assertEqual(
            vcpkg.triplet_for_toolchain(self._tc('linux', 'x86_64', 'gcc')),
            'x64-linux')

    def test_apple_clang_arm(self):
        self.assertEqual(
            vcpkg.triplet_for_toolchain(self._tc('darwin', 'aarch64', 'clang')),
            'arm64-osx')

    def test_msvc(self):
        self.assertEqual(
            vcpkg.triplet_for_toolchain(self._tc('windows', 'x64', 'msvc')),
            'x64-windows-static')


class _Referrer:
    def __init__(self, db=None, path='app/foo'):
        self.target_database = db if db is not None else {}
        self.path = path
        self.errors = []
        self.blade = mock.Mock()
        self.blade.get_build_toolchain.return_value = mock.Mock()
        self.blade.get_build_dir.return_value = 'build64'

    def error(self, msg):
        self.errors.append(msg)


class HandlerTest(unittest.TestCase):

    def _cfg(self, **over):
        # manage=False here pins the install location to root='/vc' so the
        # handler-logic assertions stay deterministic; install_location's
        # manage=True path is covered in vcpkg_setup_test + the case below.
        cfg = {'packages': _WHITELIST, 'triplet': 'x64-linux', 'root': '/vc',
               'manage': False, 'install_dir': '.cache/vcpkg'}
        cfg.update(over)
        return cfg

    def test_whitelist_error_short_circuits(self):
        r = _Referrer()
        with mock.patch('blade.config.get_section', return_value=self._cfg()), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            key = vcpkg._vcpkg_dep_handler(r, 'boost:boost')
        self.assertIsNone(key)
        self.assertEqual(len(r.errors), 1)
        MockVL.assert_not_called()
        r.blade.register_target.assert_not_called()

    def test_valid_creates_and_registers(self):
        r = _Referrer()
        with mock.patch('blade.config.get_section', return_value=self._cfg()), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            key = vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        self.assertEqual(key, 'vcpkg#fmt:fmt')
        MockVL.assert_called_once()
        # port, lib, key, lib_dir, include_dir, header_only
        args = MockVL.call_args[0]
        self.assertEqual(args[0], 'fmt')
        self.assertEqual(args[1], 'fmt')
        self.assertEqual(args[2], 'vcpkg#fmt:fmt')
        self.assertFalse(args[5])
        r.blade.register_target.assert_called_once()

    def test_msvc_debug_passes_debug_lib_dir(self):
        # The handler forwards the build profile; an MSVC-ABI debug build must
        # hand VcpkgLibrary the debug/lib dir (include stays shared).
        r = _Referrer()
        r.blade.get_options.return_value.profile = 'debug'
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(triplet='x64-windows')), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        args = MockVL.call_args[0]  # port, lib, key, lib_dir, include_dir, header_only
        # endswith (not ==): install_location abspath()s the root, which differs
        # by platform (e.g. '/vc' -> 'C:\\vc' on Windows).
        self.assertTrue(args[3].endswith(
            os.path.join('installed', 'x64-windows', 'debug', 'lib')), args[3])
        self.assertTrue(args[4].endswith(
            os.path.join('installed', 'x64-windows', 'include')), args[4])

    def test_already_registered_is_reused(self):
        r = _Referrer(db={'vcpkg#fmt:fmt': object()})
        with mock.patch('blade.config.get_section', return_value=self._cfg()), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            key = vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        self.assertEqual(key, 'vcpkg#fmt:fmt')
        MockVL.assert_not_called()
        r.blade.register_target.assert_not_called()

    def test_direct_use_allowed_blocks_outside_referrer(self):
        # With an allowlist set, a referrer outside it cannot use vcpkg# directly.
        r = _Referrer(path='app/foo')
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(direct_use_allowed=['thirdparty'])), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            key = vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        self.assertIsNone(key)
        self.assertEqual(len(r.errors), 1)
        self.assertIn('direct_use_allowed', r.errors[0])
        MockVL.assert_not_called()

    def test_direct_use_allowed_permits_inside_referrer(self):
        # A referrer under an allowed subtree (here '//thirdparty/...') is fine.
        r = _Referrer(path='thirdparty/fmt')
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(direct_use_allowed=['//thirdparty'])), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            key = vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        self.assertEqual(key, 'vcpkg#fmt:fmt')
        MockVL.assert_called_once()

    def test_direct_use_allowed_empty_permits_anywhere(self):
        # The default empty allowlist imposes no restriction.
        r = _Referrer(path='app/foo')
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(direct_use_allowed=[])), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            key = vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        self.assertEqual(key, 'vcpkg#fmt:fmt')

    def test_path_under(self):
        self.assertTrue(vcpkg._path_under('thirdparty/fmt', ['thirdparty']))
        self.assertTrue(vcpkg._path_under('thirdparty', ['//thirdparty']))
        self.assertTrue(vcpkg._path_under('a/b/c', ['x', 'a/b']))
        self.assertFalse(vcpkg._path_under('thirdpartyx/fmt', ['thirdparty']))
        self.assertFalse(vcpkg._path_under('app/foo', ['thirdparty']))

    def test_auto_triplet_derived_from_toolchain(self):
        r = _Referrer()
        tc = r.blade.get_build_toolchain.return_value
        tc.target_os, tc.target_arch = 'linux', 'x86_64'
        tc.cc_is = lambda v: v == 'gcc'
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(triplet='auto')), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        # lib_dir reflects the auto-derived x64-linux triplet.
        self.assertEqual(MockVL.call_args[0][3], '/vc/installed/x64-linux/lib')

    def test_manage_true_uses_hermetic_tree(self):
        r = _Referrer()
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(manage=True, triplet='x64-linux')), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        lib_dir = MockVL.call_args[0][3]
        # Hermetic tree under the build dir, with the blade- overlay triplet.
        self.assertTrue(lib_dir.endswith(
            os.path.join('build64', '.cache/vcpkg', 'installed',
                         'blade-x64-linux', 'lib')))

    def test_auto_port_passes_shared_dynamic_lib_dir(self):
        # An 'auto' port (managed mode) gets its shared lib from the separate
        # `-shared` tree; the handler points dynamic_lib_dir there.
        r = _Referrer()
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(manage=True, triplet='x64-linux',
                                               packages={'glog': {'linkage': 'auto'}})), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            vcpkg._vcpkg_dep_handler(r, 'glog:glog')
        kw = MockVL.call_args[1]
        self.assertEqual(kw['linkage'], 'auto')
        self.assertTrue(kw['dynamic_lib_dir'].endswith(
            os.path.join('shared', 'installed', 'blade-x64-linux-shared', 'lib')),
            kw['dynamic_lib_dir'])

    def test_static_port_dynamic_lib_dir_falls_back_to_main(self):
        r = _Referrer()
        with mock.patch('blade.config.get_section',
                        return_value=self._cfg(packages={'fmt': '10.2.1'})), \
             mock.patch('blade.cc_targets.VcpkgLibrary') as MockVL:
            vcpkg._vcpkg_dep_handler(r, 'fmt:fmt')
        kw = MockVL.call_args[1]
        self.assertEqual(kw['linkage'], 'static')
        self.assertEqual(kw['dynamic_lib_dir'], MockVL.call_args[0][3])

    def test_registered_as_vcpkg_scheme(self):
        # Importing blade.vcpkg wires the provider into target's registry.
        from blade import target as target_mod
        self.assertIn('vcpkg', target_mod._dep_scheme_providers)


if __name__ == '__main__':
    unittest.main()
