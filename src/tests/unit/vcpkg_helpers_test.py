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
import sys
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


if __name__ == '__main__':
    unittest.main()
