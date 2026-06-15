#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for the pure vcpkg helpers (issue #1236, PR3).

"""Tests triplet derivation and pkg-config parsing in blade.vcpkg.

These are the provider-independent pieces the vcpkg dependency handler builds
on; the handler + VcpkgLibrary target (which need a mock install tree) land in
the next PR.
"""

import os
import shutil
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import vcpkg  # noqa: E402


class TripletTest(unittest.TestCase):
    """Phase 1 returns the vanilla triplet a host's `vcpkg install` uses."""

    def test_linux_x64(self):
        self.assertEqual(vcpkg.triplet_for('linux', 'x86_64'), 'x64-linux')

    def test_linux_arm64(self):
        self.assertEqual(vcpkg.triplet_for('linux', 'aarch64'), 'arm64-linux')

    def test_darwin_arm64(self):
        # Apple Silicon: cc -dumpmachine yields arm64 -> canonical aarch64.
        self.assertEqual(vcpkg.triplet_for('darwin', 'aarch64'), 'arm64-osx')

    def test_darwin_x64(self):
        self.assertEqual(vcpkg.triplet_for('darwin', 'x86_64'), 'x64-osx')

    def test_windows_msvc_defaults_static(self):
        # blade links static; vcpkg's default windows triplet is dynamic, so
        # 'auto' must resolve to the -static variant.
        self.assertEqual(vcpkg.triplet_for('windows', 'x64', vendor='msvc'),
                         'x64-windows-static')

    def test_windows_mingw(self):
        self.assertEqual(vcpkg.triplet_for('windows', 'x86_64', vendor='gcc'),
                         'x64-mingw-static')

    def test_dynamic_variants(self):
        self.assertEqual(vcpkg.triplet_for('linux', 'x86_64', dynamic=True),
                         'x64-linux-dynamic')
        self.assertEqual(vcpkg.triplet_for('windows', 'x64', vendor='msvc', dynamic=True),
                         'x64-windows')

    def test_unsupported_returns_none(self):
        self.assertIsNone(vcpkg.triplet_for('plan9', 'x86_64'))
        self.assertIsNone(vcpkg.triplet_for('linux', 'sparc'))


_OPENSSL_PC = """\
prefix=/work/build64/.cache/vcpkg/installed/x64-linux
exec_prefix=${prefix}
libdir=${prefix}/lib
includedir=${prefix}/include

Name: OpenSSL-libssl
Description: Secure Sockets Layer and cryptography libraries
Version: 3.2.1
Requires.private: libcrypto >= 3.2.1
Libs: -L${libdir} -lssl
Libs.private: -ldl -pthread
Cflags: -I${includedir}
"""

_HEADER_ONLY_PC = """\
prefix=/x
includedir=${prefix}/include
Name: nlohmann_json
Version: 3.11.3
Cflags: -I${includedir}
"""


class ParsePkgConfigTest(unittest.TestCase):

    def test_basic_fields_and_expansion(self):
        pc = vcpkg.parse_pkgconfig(_OPENSSL_PC)
        self.assertEqual(pc['name'], 'OpenSSL-libssl')
        self.assertEqual(pc['version'], '3.2.1')
        # ${libdir} -> ${prefix}/lib -> the absolute prefix; expansion is nested.
        self.assertIn('-L/work/build64/.cache/vcpkg/installed/x64-linux/lib',
                      pc['libs'])

    def test_l_libs_extracted(self):
        pc = vcpkg.parse_pkgconfig(_OPENSSL_PC)
        self.assertEqual(pc['l_libs'], ['ssl'])

    def test_requires_private_strips_version(self):
        pc = vcpkg.parse_pkgconfig(_OPENSSL_PC)
        self.assertEqual(pc['requires_private'], ['libcrypto'])
        self.assertEqual(pc['requires'], [])

    def test_libs_private_system_libs(self):
        pc = vcpkg.parse_pkgconfig(_OPENSSL_PC)
        # -ldl -> 'dl'; bare '-pthread' is not a -l form and is left in tokens.
        self.assertEqual(pc['l_private'], ['dl'])
        self.assertIn('-pthread', pc['libs_private'])

    def test_libs_private_msvc_dot_lib_form(self):
        # vcpkg/OpenSSL on Windows list system libs as bare `foo.lib` tokens, not
        # `-lfoo`; the `.lib` is stripped to a uniform bare name.
        pc = vcpkg.parse_pkgconfig(
            'Name: libcrypto\nLibs.private: ws2_32.lib advapi32.lib crypt32.lib\n')
        self.assertEqual(pc['l_private'], ['ws2_32', 'advapi32', 'crypt32'])

    def test_header_only_has_no_libs(self):
        pc = vcpkg.parse_pkgconfig(_HEADER_ONLY_PC)
        self.assertEqual(pc['l_libs'], [])
        self.assertEqual(pc['requires'], [])
        self.assertIn('-I/x/include', pc['cflags'])

    def test_comma_and_space_separated_requires(self):
        pc = vcpkg.parse_pkgconfig(
            'Name: x\nRequires: a >= 1.0, b, c\n')
        self.assertEqual(pc['requires'], ['a', 'b', 'c'])

    def test_value_with_equals_not_treated_as_var(self):
        # A keyword value containing '=' must not be misread as a variable def.
        pc = vcpkg.parse_pkgconfig('Name: x\nCflags: -DFOO=1 -I/i\n')
        self.assertIn('-DFOO=1', pc['cflags'])
        self.assertEqual(pc['name'], 'x')

    def test_spaced_dash_l(self):
        pc = vcpkg.parse_pkgconfig('Name: x\nLibs: -L/d -l ssl -lcrypto\n')
        self.assertEqual(pc['l_libs'], ['ssl', 'crypto'])

    def test_empty_input(self):
        pc = vcpkg.parse_pkgconfig('')
        self.assertEqual(pc['name'], '')
        self.assertEqual(pc['l_libs'], [])


class PortSystemLibsTest(unittest.TestCase):
    """`port_system_libs` reads a port's installed .pc Libs.private and returns
    the OS/SDK libs a consumer must link (issue #1322), excluding sibling vcpkg
    libraries it finds as archives in the lib dir."""

    TRIPLET = 'blade-x64-windows-static'

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.installed = os.path.join(self.root, 'installed')
        self.tdir = os.path.join(self.installed, self.TRIPLET)
        self.lib_dir = os.path.join(self.tdir, 'lib')
        self.pkgconfig = os.path.join(self.lib_dir, 'pkgconfig')
        os.makedirs(self.pkgconfig)

    def _write_pc(self, name, libs_private):
        path = os.path.join(self.pkgconfig, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('Name: %s\nLibs.private: %s\n' % (name, libs_private))
        return '%s/lib/pkgconfig/%s' % (self.TRIPLET, name)

    def _write_list(self, port, version, rel_paths):
        info = os.path.join(self.installed, 'vcpkg', 'info')
        os.makedirs(info, exist_ok=True)
        fname = '%s_%s_%s.list' % (port, version, self.TRIPLET)
        with open(os.path.join(info, fname), 'w', encoding='utf-8') as f:
            f.write('\n'.join(rel_paths) + '\n')

    def _touch(self, name):
        open(os.path.join(self.lib_dir, name), 'w').close()

    def test_collects_private_system_libs(self):
        rel = self._write_pc('libglog.pc', '-ldbghelp')
        self._write_list('glog', '0.6.0', [self.TRIPLET + '/lib/', rel])
        self.assertEqual(
            vcpkg.port_system_libs(self.root, self.TRIPLET, 'glog', self.lib_dir),
            ['dbghelp'])

    def test_excludes_sibling_vcpkg_libs(self):
        # glog's Libs.private references gflags (a sibling vcpkg lib, present as
        # an archive) plus dbghelp (a real system lib). Only dbghelp is returned.
        rel = self._write_pc('libglog.pc', '-lgflags -ldbghelp')
        self._touch('gflags.lib')
        self._write_list('glog', '0.6.0', [rel])
        self.assertEqual(
            vcpkg.port_system_libs(self.root, self.TRIPLET, 'glog', self.lib_dir),
            ['dbghelp'])

    def test_sorted_and_deduplicated(self):
        r1 = self._write_pc('libssl.pc', '-lcrypt32 -lws2_32')
        r2 = self._write_pc('libcrypto.pc', '-lws2_32 -ladvapi32')
        self._write_list('openssl', '3.2.1', [r1, r2])
        self.assertEqual(
            vcpkg.port_system_libs(self.root, self.TRIPLET, 'openssl', self.lib_dir),
            ['advapi32', 'crypt32', 'ws2_32'])

    def test_msvc_dot_lib_private_libs(self):
        # The real OpenSSL-on-Windows case: Libs.private uses `foo.lib` tokens.
        rel = self._write_pc('libcrypto.pc', 'ws2_32.lib advapi32.lib crypt32.lib')
        self._write_list('openssl', '3.5.0', [rel])
        self.assertEqual(
            vcpkg.port_system_libs(self.root, self.TRIPLET, 'openssl', self.lib_dir),
            ['advapi32', 'crypt32', 'ws2_32'])

    def test_missing_metadata_returns_empty(self):
        # No info .list for the port -> no system libs, no error.
        self.assertEqual(
            vcpkg.port_system_libs(self.root, self.TRIPLET, 'absent', self.lib_dir),
            [])

    def test_prefix_named_port_not_matched(self):
        # A port whose name prefixes another ('gflag' vs 'gflags') must not pick
        # up the other's list: the '_' separator anchors the glob.
        rel = self._write_pc('libgflags.pc', '-lshlwapi')
        self._write_list('gflags', '2.2.2', [rel])
        self.assertEqual(
            vcpkg.port_system_libs(self.root, self.TRIPLET, 'gflag', self.lib_dir),
            [])


if __name__ == '__main__':
    unittest.main()
