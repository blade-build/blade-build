#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the MSVC side of the cc check_undefined static check.

On MSVC the archives are COFF ``.lib`` files and ``nm`` is unavailable, so
symbols are read with ``dumpbin``:

  * system import libs -> ``dumpbin /linkermember`` gives the defined externals
    (system_symbols._dumpbin_defined_symbols),
  * a target's own ``.lib`` -> ``dumpbin /symbols`` separates undefined from
    defined externals (builtin_tools._dumpbin_extract_externals).

These tests feed canned dumpbin output (so they run on any platform) and pin
the parsers, plus the MSVC dispatch in resolve_lib_paths / _nm_* wrappers.
"""

import os
import subprocess
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import builtin_tools  # noqa: E402
from blade import system_symbols  # noqa: E402


# A realistic `dumpbin /linkermember:1` dump of an import lib: header rows, the
# "<N> public symbols" line, a blank line, then "<hex-offset> <symbol>" rows.
_LINKERMEMBER_OUT = """\
Microsoft (R) COFF/PE Dumper

Dump of file kernel32.lib

File Type: LIBRARY

Archive member name at 8: /
         uid
         gid
       0 mode
   128B4 size
    2795 public symbols

    251F2 __IMPORT_DESCRIPTOR_KERNEL32
    25956 AddConsoleAliasA
    25956 __imp_AddConsoleAliasA
    25A32 AddDllDirectory
"""

# A realistic `dumpbin /symbols` dump of a static lib with one undefined ref,
# two definitions, plus non-external noise that must be ignored.
_SYMBOLS_OUT = """\
Microsoft (R) COFF/PE Dumper

Dump of file a.lib

COFF SYMBOL TABLE
000 00000000 SECT1  notype       Static       | .text
007 00000000 SECT1  notype       Label        | $LN3
008 00000000 UNDEF  notype ()    External     | ?helper@@YAHXZ (int __cdecl helper(void))
009 00000000 SECT3  notype ()    External     | ?use@@YAHXZ (int __cdecl use(void))
00A 00000020 SECT3  notype ()    External     | ?defined_here@@YAHXZ (int __cdecl defined_here(void))
"""


class IsHexOffsetTest(unittest.TestCase):
    def test_accepts_hex(self):
        self.assertTrue(system_symbols._is_hexoffset('251F2'))
        self.assertTrue(system_symbols._is_hexoffset('0'))

    def test_rejects_non_hex(self):
        self.assertFalse(system_symbols._is_hexoffset('public'))
        self.assertFalse(system_symbols._is_hexoffset('__imp_foo'))
        self.assertFalse(system_symbols._is_hexoffset(''))


class DumpbinDefinedSymbolsTest(unittest.TestCase):
    """system_symbols._dumpbin_defined_symbols parses /linkermember output."""

    def _run(self, text):
        with mock.patch.object(subprocess, 'check_output', return_value=text):
            return system_symbols._dumpbin_defined_symbols('dumpbin', 'kernel32.lib')

    def test_collects_symbols_after_public_symbols_line(self):
        self.assertEqual(
            self._run(_LINKERMEMBER_OUT),
            {'__IMPORT_DESCRIPTOR_KERNEL32', 'AddConsoleAliasA',
             '__imp_AddConsoleAliasA', 'AddDllDirectory'})

    def test_header_rows_before_marker_are_ignored(self):
        # 'size', 'mode', etc. (hex-prefixed header rows) precede the marker and
        # must not leak in.
        syms = self._run(_LINKERMEMBER_OUT)
        self.assertNotIn('size', syms)
        self.assertNotIn('mode', syms)

    def test_dumpbin_failure_returns_empty(self):
        with mock.patch.object(subprocess, 'check_output',
                               side_effect=FileNotFoundError(2, 'no dumpbin')):
            self.assertEqual(
                system_symbols._dumpbin_defined_symbols('dumpbin', 'x.lib'), set())

    def test_called_process_error_returns_empty(self):
        with mock.patch.object(subprocess, 'check_output',
                               side_effect=subprocess.CalledProcessError(1, 'dumpbin')):
            self.assertEqual(
                system_symbols._dumpbin_defined_symbols('dumpbin', 'x.lib'), set())


class DumpbinExtractExternalsTest(unittest.TestCase):
    """builtin_tools._dumpbin_extract_externals parses /symbols output into
    (undefined, defined)."""

    def _run(self, text):
        with mock.patch.object(subprocess, 'check_output',
                               return_value=text.encode('utf-8')):
            return builtin_tools._dumpbin_extract_externals('dumpbin', 'a.lib')

    def test_splits_undefined_and_defined(self):
        undef, defd = self._run(_SYMBOLS_OUT)
        self.assertEqual(undef, {'?helper@@YAHXZ'})
        self.assertEqual(defd, {'?use@@YAHXZ', '?defined_here@@YAHXZ'})

    def test_static_and_label_rows_ignored(self):
        # '.text' (Static) and '$LN3' (Label) are not External -> dropped.
        undef, defd = self._run(_SYMBOLS_OUT)
        self.assertNotIn('.text', undef | defd)
        self.assertNotIn('$LN3', undef | defd)

    def test_demangled_comment_dropped(self):
        # The "(int __cdecl helper(void))" comment after the name must not be
        # part of the symbol.
        undef, _ = self._run(_SYMBOLS_OUT)
        self.assertEqual(undef, {'?helper@@YAHXZ'})

    def test_dumpbin_missing_returns_empty(self):
        # Patch console.error so the expected "dumpbin not found" diagnostic
        # doesn't print as noise during the test run.
        with mock.patch.object(subprocess, 'check_output',
                               side_effect=FileNotFoundError(2, 'no dumpbin')), \
             mock.patch.object(builtin_tools.console, 'error'):
            self.assertEqual(
                builtin_tools._dumpbin_extract_externals('dumpbin', 'a.lib'),
                (set(), set()))


class _FakeMsvcToolchain:
    """Minimal toolchain stub for the MSVC dispatch tests."""
    cc = 'cl.exe'
    dumpbin = 'dumpbin.exe'
    target_os = 'windows'

    def __init__(self, lib_paths):
        self._lib_paths = lib_paths

    def cc_is(self, vendor):
        return vendor == 'msvc'

    def get_system_lib_paths(self):
        return self._lib_paths


class ResolveLibPathsMsvcTest(unittest.TestCase):
    """resolve_lib_paths searches the toolchain's lib dirs for <alias>.lib on
    MSVC (cl has no -print-file-name)."""

    def test_finds_lib_in_search_paths(self):
        tc = _FakeMsvcToolchain([r'C:\sdk\lib', r'C:\msvc\lib'])
        hit = os.path.join(r'C:\msvc\lib', 'oldnames.lib')
        with mock.patch('os.path.isfile', side_effect=lambda p: p == hit), \
             mock.patch('os.path.realpath', side_effect=lambda p: p):
            self.assertEqual(system_symbols.resolve_lib_paths(tc, 'oldnames'), [hit])

    def test_unresolved_returns_empty(self):
        tc = _FakeMsvcToolchain([r'C:\sdk\lib'])
        with mock.patch('os.path.isfile', return_value=False):
            self.assertEqual(system_symbols.resolve_lib_paths(tc, 'nope'), [])

    def test_nm_defined_externals_dispatches_to_dumpbin(self):
        tc = _FakeMsvcToolchain([])
        with mock.patch.object(system_symbols, '_dumpbin_defined_symbols',
                               return_value={'printf'}) as m:
            out = system_symbols._nm_defined_externals(r'C:\x\msvcrt.lib', tc)
        self.assertEqual(out, {'printf'})
        m.assert_called_once_with('dumpbin.exe', r'C:\x\msvcrt.lib')


class NmExtractExternalsDispatchTest(unittest.TestCase):
    """builtin_tools._nm_extract_externals routes to dumpbin when given one."""

    def test_dumpbin_path_routes_to_dumpbin(self):
        with mock.patch.object(builtin_tools, '_dumpbin_extract_externals',
                               return_value=({'u'}, {'d'})) as m:
            out = builtin_tools._nm_extract_externals('a.lib', dumpbin='dumpbin.exe')
        self.assertEqual(out, ({'u'}, {'d'}))
        m.assert_called_once_with('dumpbin.exe', 'a.lib')


if __name__ == '__main__':
    unittest.main()
