#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for vcpkg manifest + overlay-triplet generation (#1236, PR5).

"""Tests the pure Phase-2 generators: synthetic vcpkg.json, the overlay triplet
that chainloads blade's compiler, and the chainload toolchain file. Writing
these files + invoking `vcpkg install` is wired separately (PR6)."""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import vcpkg  # noqa: E402


class ManifestTest(unittest.TestCase):

    def test_string_version_becomes_dep_plus_override(self):
        m = vcpkg.manifest_json({'fmt': '10.2.1'})
        self.assertEqual(m['dependencies'], ['fmt'])
        self.assertEqual(m['overrides'], [{'name': 'fmt', 'version': '10.2.1'}])

    def test_features_dep_object(self):
        m = vcpkg.manifest_json(
            {'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']}})
        self.assertEqual(m['dependencies'],
                         [{'name': 'curl', 'features': ['ssl', 'http2']}])
        self.assertEqual(m['overrides'], [{'name': 'curl', 'version': '8.5.0'}])

    def test_baseline_included_when_set(self):
        m = vcpkg.manifest_json({'fmt': '10.2.1'}, baseline='2024-12-15')
        self.assertEqual(m['builtin-baseline'], '2024-12-15')

    def test_no_baseline_key_when_empty(self):
        m = vcpkg.manifest_json({'fmt': '10.2.1'})
        self.assertNotIn('builtin-baseline', m)

    def test_deterministic_order(self):
        # Sorted by port so the generated manifest is stable across runs.
        m = vcpkg.manifest_json({'zlib': '1.3', 'fmt': '10.2.1'})
        self.assertEqual(m['dependencies'], ['fmt', 'zlib'])

    def test_version_optional(self):
        # A featureful spec without a version -> dep object, no override.
        m = vcpkg.manifest_json({'x': {'features': ['a']}})
        self.assertEqual(m['dependencies'], [{'name': 'x', 'features': ['a']}])
        self.assertNotIn('overrides', m)

    def test_empty(self):
        self.assertEqual(vcpkg.manifest_json({}), {'dependencies': []})


class ConfigurationTest(unittest.TestCase):

    def test_none_when_no_registries(self):
        self.assertIsNone(vcpkg.configuration_json([]))

    def test_registries_passed_through(self):
        regs = [{'kind': 'git', 'repository': 'https://x', 'baseline': 'abc'}]
        self.assertEqual(vcpkg.configuration_json(regs), {'registries': regs})


class OverlayTripletTest(unittest.TestCase):

    def test_name(self):
        self.assertEqual(vcpkg.overlay_triplet_name('x64-linux'), 'blade-x64-linux')

    def test_linux(self):
        # Mirrors vcpkg's stock x64-linux triplet (+ chainload). The system
        # name is how vcpkg sets VCPKG_TARGET_IS_LINUX, which ports branch on.
        t = vcpkg.overlay_triplet_cmake('linux', 'x86_64')
        self.assertIn('set(VCPKG_TARGET_ARCHITECTURE x64)', t)
        self.assertIn('set(VCPKG_LIBRARY_LINKAGE static)', t)
        self.assertIn('set(VCPKG_CMAKE_SYSTEM_NAME Linux)', t)
        self.assertIn('VCPKG_CHAINLOAD_TOOLCHAIN_FILE', t)
        self.assertIn('../blade-chainload.cmake', t)

    def test_darwin_arm(self):
        # Mirrors stock arm64-osx: Darwin (native, not cross) + OSX arch.
        t = vcpkg.overlay_triplet_cmake('darwin', 'aarch64')
        self.assertIn('set(VCPKG_TARGET_ARCHITECTURE arm64)', t)
        self.assertIn('set(VCPKG_CMAKE_SYSTEM_NAME Darwin)', t)
        self.assertIn('set(VCPKG_OSX_ARCHITECTURES arm64)', t)

    def test_windows_omits_system_name(self):
        # Windows is vcpkg's default host; its stock triplets set no system name.
        t = vcpkg.overlay_triplet_cmake('windows', 'x64')
        self.assertNotIn('VCPKG_CMAKE_SYSTEM_NAME', t)
        self.assertIn('set(VCPKG_TARGET_ARCHITECTURE x64)', t)

    def test_dynamic_linkage(self):
        t = vcpkg.overlay_triplet_cmake('linux', 'x86_64', library_linkage='dynamic')
        self.assertIn('set(VCPKG_LIBRARY_LINKAGE dynamic)', t)

    def test_unsupported_returns_none(self):
        self.assertIsNone(vcpkg.overlay_triplet_cmake('plan9', 'x86_64'))
        self.assertIsNone(vcpkg.overlay_triplet_cmake('linux', 'sparc'))


class PortOptionsTest(unittest.TestCase):

    def test_bare_version_defaults(self):
        self.assertEqual(vcpkg.port_options({'fmt': '7.1.3'}, 'fmt'),
                         ('static', False, None))

    def test_dynamic_linkage(self):
        self.assertEqual(
            vcpkg.port_options({'gflags': {'linkage': 'dynamic'}}, 'gflags'),
            ('dynamic', False, None))

    def test_link_all_symbols(self):
        self.assertEqual(
            vcpkg.port_options({'g': {'link_all_symbols': True}}, 'g'),
            ('static', True, None))

    def test_include_prefix(self):
        self.assertEqual(
            vcpkg.port_options({'snappy': {'include_prefix': 'snappy'}}, 'snappy'),
            ('static', False, 'snappy'))

    def test_include_prefix_dict(self):
        # prefix -> vcpkg subdir mapping (e.g. "thirdparty/glog" -> include/glog).
        self.assertEqual(
            vcpkg.port_options(
                {'glog': {'include_prefix': {'thirdparty/glog': 'glog'}}}, 'glog'),
            ('static', False, {'thirdparty/glog': 'glog'}))

    def test_dynamic_ports_sorted(self):
        pkgs = {'fmt': '7', 'gflags': {'linkage': 'dynamic'},
                'glog': {'linkage': 'dynamic'}, 'z': {'linkage': 'static'}}
        self.assertEqual(vcpkg.dynamic_ports(pkgs), ['gflags', 'glog'])

    def test_overlay_per_port_dynamic_override(self):
        t = vcpkg.overlay_triplet_cmake('darwin', 'aarch64', dynamic_ports=['gflags'])
        self.assertIn('set(VCPKG_LIBRARY_LINKAGE static)', t)
        self.assertIn('if(PORT STREQUAL "gflags")', t)
        self.assertIn('    set(VCPKG_LIBRARY_LINKAGE dynamic)', t)
        self.assertIn('endif()', t)

    def test_overlay_no_dynamic_ports_has_no_guard(self):
        self.assertNotIn('if(PORT STREQUAL',
                         vcpkg.overlay_triplet_cmake('linux', 'x86_64'))

    def test_port_cmake_options(self):
        pkgs = {'fmt': '7', 'snappy': {'cmake_options': ['-DSNAPPY_WITH_RTTI=ON']}}
        self.assertEqual(vcpkg.port_cmake_options(pkgs),
                         {'snappy': ['-DSNAPPY_WITH_RTTI=ON']})

    def test_overlay_per_port_cmake_options(self):
        t = vcpkg.overlay_triplet_cmake(
            'darwin', 'aarch64',
            cmake_options={'snappy': ['-DSNAPPY_WITH_RTTI=ON']})
        self.assertIn('if(PORT STREQUAL "snappy")', t)
        self.assertIn('set(VCPKG_CMAKE_CONFIGURE_OPTIONS "-DSNAPPY_WITH_RTTI=ON")', t)


class ChainloadTest(unittest.TestCase):

    def test_compiler_and_flags(self):
        c = vcpkg.chainload_cmake('/usr/bin/gcc', '/usr/bin/g++',
                                  c_flags='-O2', cxx_flags='-O2 -std=c++17')
        self.assertIn('set(CMAKE_C_COMPILER "/usr/bin/gcc")', c)
        self.assertIn('set(CMAKE_CXX_COMPILER "/usr/bin/g++")', c)
        self.assertIn('set(CMAKE_C_FLAGS_INIT "-O2")', c)
        self.assertIn('set(CMAKE_CXX_FLAGS_INIT "-O2 -std=c++17")', c)


if __name__ == '__main__':
    unittest.main()
