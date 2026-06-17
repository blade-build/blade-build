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


def _overlay(*args, **kwargs):
    """overlay_triplet_cmake for a supported os/arch -- typed non-None."""
    text = vcpkg.overlay_triplet_cmake(*args, **kwargs)
    assert text is not None
    return text


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
        t = _overlay('linux', 'x86_64')
        self.assertIn('set(VCPKG_TARGET_ARCHITECTURE x64)', t)
        self.assertIn('set(VCPKG_LIBRARY_LINKAGE static)', t)
        # Release-only: blade links the release tree, never debug/.
        self.assertIn('set(VCPKG_BUILD_TYPE release)', t)
        # -fPIC so a static .a can be linked into a .so (ELF needs PIC).
        self.assertIn('set(VCPKG_C_FLAGS "-fPIC")', t)
        self.assertIn('set(VCPKG_CXX_FLAGS "-fPIC")', t)
        self.assertIn('set(VCPKG_CMAKE_SYSTEM_NAME Linux)', t)
        self.assertIn('VCPKG_CHAINLOAD_TOOLCHAIN_FILE', t)
        self.assertIn('../blade-chainload.cmake', t)

    def test_darwin_arm(self):
        # Mirrors stock arm64-osx: Darwin (native, not cross) + OSX arch.
        t = _overlay('darwin', 'aarch64')
        self.assertIn('set(VCPKG_TARGET_ARCHITECTURE arm64)', t)
        self.assertIn('set(VCPKG_CMAKE_SYSTEM_NAME Darwin)', t)
        self.assertIn('set(VCPKG_OSX_ARCHITECTURES arm64)', t)

    def test_windows_omits_system_name(self):
        # Windows is vcpkg's default host; its stock triplets set no system name.
        t = _overlay('windows', 'x64')
        self.assertNotIn('VCPKG_CMAKE_SYSTEM_NAME', t)
        self.assertIn('set(VCPKG_TARGET_ARCHITECTURE x64)', t)
        # -fPIC is meaningless on Windows (MSVC rejects it, MinGW ignores+warns).
        self.assertNotIn('-fPIC', t)

    def test_dynamic_linkage(self):
        t = _overlay('linux', 'x86_64', library_linkage='dynamic')
        self.assertIn('set(VCPKG_LIBRARY_LINKAGE dynamic)', t)

    def test_unsupported_returns_none(self):
        self.assertIsNone(vcpkg.overlay_triplet_cmake('plan9', 'x86_64'))
        self.assertIsNone(vcpkg.overlay_triplet_cmake('linux', 'sparc'))

    def test_build_type_release_by_default(self):
        self.assertIn('set(VCPKG_BUILD_TYPE release)', _overlay('windows', 'x64'))

    def test_build_type_none_omits_the_line(self):
        # An MSVC-ABI debug build needs both release + debug -> no VCPKG_BUILD_TYPE.
        self.assertNotIn('VCPKG_BUILD_TYPE',
                         _overlay('windows', 'x64', build_type=None))

    def test_chainload_present_by_default(self):
        self.assertIn('VCPKG_CHAINLOAD_TOOLCHAIN_FILE', _overlay('linux', 'x86_64'))

    def test_chainload_omitted_when_disabled(self):
        # MSVC uses vcpkg's native toolchain -> no chainload, else vcpkg runs in
        # `external` toolset mode and skips its MSVC env setup (mt/rc/INCLUDE/LIB),
        # so ports fail to link.
        self.assertNotIn('VCPKG_CHAINLOAD_TOOLCHAIN_FILE',
                         _overlay('windows', 'x64', chainload=False))


class MsvcDebugGateTest(unittest.TestCase):
    """The MSVC-ABI debug gate (issue #1315): is_msvc_abi_triplet /
    vcpkg_build_type / lib_subdir."""

    def test_is_msvc_abi_triplet_true_for_windows_family(self):
        for t in ('x64-windows', 'x64-windows-static', 'blade-x64-windows',
                  'blade-x64-windows-shared'):
            self.assertTrue(vcpkg.is_msvc_abi_triplet(t), t)

    def test_is_msvc_abi_triplet_false_for_mingw_posix_none(self):
        for t in ('x64-mingw-dynamic', 'x64-mingw-static', 'x64-linux',
                  'arm64-osx', '', None):
            self.assertFalse(vcpkg.is_msvc_abi_triplet(t), t)

    def test_vcpkg_build_type_release_except_msvc_debug(self):
        self.assertEqual(vcpkg.vcpkg_build_type('x64-windows', 'release'), 'release')
        self.assertEqual(vcpkg.vcpkg_build_type('x64-linux', 'debug'), 'release')
        self.assertEqual(vcpkg.vcpkg_build_type('x64-mingw-dynamic', 'debug'),
                         'release')
        # MSVC-ABI debug -> build both (None), so debug libs exist to link.
        self.assertIsNone(vcpkg.vcpkg_build_type('x64-windows', 'debug'))
        self.assertIsNone(vcpkg.vcpkg_build_type('blade-x64-windows', 'debug'))

    def test_lib_subdir(self):
        self.assertEqual(vcpkg.lib_subdir('x64-windows', 'release'), 'lib')
        self.assertEqual(vcpkg.lib_subdir('x64-linux', 'debug'), 'lib')
        self.assertEqual(vcpkg.lib_subdir('x64-mingw-dynamic', 'debug'), 'lib')
        self.assertEqual(vcpkg.lib_subdir('x64-windows', 'debug'),
                         os.path.join('debug', 'lib'))


class PortOptionsTest(unittest.TestCase):

    def test_bare_version_defaults_to_auto(self):
        # Default linkage is 'auto' (cc_library-like): static for static-link
        # consumers, shared on demand for dynamic-link ones.
        self.assertEqual(vcpkg.port_options({'fmt': '7.1.3'}, 'fmt'),
                         ('auto', False, None))

    def test_dict_without_linkage_defaults_to_auto(self):
        self.assertEqual(
            vcpkg.port_options({'fmt': {'version': '7.1.3'}}, 'fmt'),
            ('auto', False, None))

    def test_dynamic_linkage(self):
        self.assertEqual(
            vcpkg.port_options({'gflags': {'linkage': 'dynamic'}}, 'gflags'),
            ('dynamic', False, None))

    def test_explicit_static_linkage(self):
        self.assertEqual(
            vcpkg.port_options({'p': {'linkage': 'static'}}, 'p'),
            ('static', False, None))

    def test_link_all_symbols(self):
        # No explicit linkage -> 'auto'.
        self.assertEqual(
            vcpkg.port_options({'g': {'link_all_symbols': True}}, 'g'),
            ('auto', True, None))

    def test_include_prefix(self):
        self.assertEqual(
            vcpkg.port_options({'snappy': {'include_prefix': 'snappy'}}, 'snappy'),
            ('auto', False, 'snappy'))

    def test_include_prefix_dict(self):
        # prefix -> vcpkg subdir mapping (e.g. "thirdparty/glog" -> include/glog).
        self.assertEqual(
            vcpkg.port_options(
                {'glog': {'include_prefix': {'thirdparty/glog': 'glog'}}}, 'glog'),
            ('auto', False, {'thirdparty/glog': 'glog'}))

    def test_auto_linkage(self):
        self.assertEqual(
            vcpkg.port_options({'glog': {'linkage': 'auto'}}, 'glog'),
            ('auto', False, None))

    def test_dynamic_ports_sorted(self):
        # 'fmt' (bare) is 'auto' by default, not 'dynamic'.
        pkgs = {'fmt': '7', 'gflags': {'linkage': 'dynamic'},
                'glog': {'linkage': 'dynamic'}, 'z': {'linkage': 'static'}}
        self.assertEqual(vcpkg.dynamic_ports(pkgs), ['gflags', 'glog'])

    def test_auto_ports_includes_default_and_excludes_static_dynamic(self):
        # Default is 'auto', so a bare version ('fmt') and a dict without an
        # explicit linkage ('lz4') are 'auto'; explicit static/dynamic are not.
        pkgs = {'fmt': '7', 'lz4': {'version': '1'},
                's': {'linkage': 'static'}, 'z': {'linkage': 'dynamic'}}
        self.assertEqual(vcpkg.auto_ports(pkgs), ['fmt', 'lz4'])
        self.assertEqual(vcpkg.dynamic_ports(pkgs), ['z'])

    def test_shared_overlay_triplet_name(self):
        self.assertEqual(vcpkg.shared_overlay_triplet_name('x64-linux'),
                         'blade-x64-linux-shared')

    def test_overlay_per_port_dynamic_override(self):
        t = _overlay('darwin', 'aarch64', dynamic_ports=['gflags'])
        self.assertIn('set(VCPKG_LIBRARY_LINKAGE static)', t)
        self.assertIn('if(PORT STREQUAL "gflags")', t)
        self.assertIn('    set(VCPKG_LIBRARY_LINKAGE dynamic)', t)
        self.assertIn('endif()', t)

    def test_overlay_no_dynamic_ports_has_no_guard(self):
        self.assertNotIn('if(PORT STREQUAL', _overlay('linux', 'x86_64'))

    def test_port_cmake_options(self):
        pkgs = {'fmt': '7', 'snappy': {'cmake_options': ['-DSNAPPY_WITH_RTTI=ON']}}
        self.assertEqual(vcpkg.port_cmake_options(pkgs),
                         {'snappy': ['-DSNAPPY_WITH_RTTI=ON']})

    def test_overlay_per_port_cmake_options(self):
        t = _overlay(
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

    def test_windows_compiler_path_uses_forward_slashes(self):
        # CMake parses '\' as an escape, so a Windows cl.exe path must be written
        # with forward slashes or every port configure fails to parse the file.
        c = vcpkg.chainload_cmake(r'C:\VS\bin\cl.exe', r'C:\VS\bin\cl.exe')
        self.assertIn('set(CMAKE_C_COMPILER "C:/VS/bin/cl.exe")', c)
        self.assertIn('set(CMAKE_CXX_COMPILER "C:/VS/bin/cl.exe")', c)
        self.assertNotIn('\\', c)

    def test_position_independent_sets_pic_property(self):
        # The triplet's VCPKG_C/CXX_FLAGS=-fPIC is dropped for CMake ports when a
        # chainload toolchain replaces vcpkg's stock one, so the PIC property must
        # be set here for a static .a to be linkable into a .so on ELF.
        c = vcpkg.chainload_cmake('/usr/bin/gcc', '/usr/bin/g++',
                                  position_independent=True)
        self.assertIn('set(CMAKE_POSITION_INDEPENDENT_CODE ON)', c)

    def test_position_independent_off_by_default(self):
        c = vcpkg.chainload_cmake('/usr/bin/gcc', '/usr/bin/g++')
        self.assertNotIn('CMAKE_POSITION_INDEPENDENT_CODE', c)


if __name__ == '__main__':
    unittest.main()
