#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors
# All rights reserved.
#
# Unit tests for the cc_macos_exports builtin tool — the translator that
# turns a GNU-ld export_map (--version-script) into an ld64
# -exported_symbols_list (plain mangled symbol names, one per line).

"""Tests for blade.builtin_tools.generate_macos_exports and its helpers.

The translator is macOS's analog of the Windows cc_windef path: it consumes
the same GNU-ld version script via the shared ``_parse_export_map`` parser,
demangles each object-file symbol via libc++abi's ``__cxa_demangle``, and
emits the matching mangled names back out (with the Mach-O leading ``_``
preserved). These tests pin:

* the on-disk output format (header line + sorted symbol list);
* the write-if-changed semantics behind ninja's ``restat`` shortcut;
* the parser→matcher pipeline against the common ``ns::class::method``
  pattern (the only pattern users practically write);
* graceful degradation when libc++abi's __cxa_demangle is unavailable
  (subprocess-less unit tests can't rely on a real demangler).

Tests that need a real demangler run only on darwin and are skipped
elsewhere.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import builtin_tools  # noqa: E402


_BASIC_EXPORT_MAP = '''
{
global:
    extern "C++" {
        mylib::Api::*;
        mylib::Create;
    };
    api_init;
local: *;
};
'''


class WriteIfChangedTest(unittest.TestCase):
    """ninja's restat optimization depends on this: unchanged outputs must
    keep their mtime so dependent edges don't relink."""

    def test_writes_when_file_missing(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'out')
            builtin_tools._write_if_changed(path, b'hello\n')
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), b'hello\n')

    def test_writes_when_content_differs(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'out')
            with open(path, 'wb') as f:
                f.write(b'old\n')
            builtin_tools._write_if_changed(path, b'new\n')
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), b'new\n')

    def test_preserves_mtime_when_unchanged(self):
        # The crux of the restat optimization. Use an older mtime that
        # would be unmistakable if write happened: a successful no-op
        # writer leaves the timestamp untouched.
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'out')
            with open(path, 'wb') as f:
                f.write(b'same\n')
            old_atime, old_mtime = 1_000_000_000, 1_000_000_000
            os.utime(path, (old_atime, old_mtime))
            builtin_tools._write_if_changed(path, b'same\n')
            self.assertEqual(int(os.stat(path).st_mtime), old_mtime)


class ParseExportMapTest(unittest.TestCase):
    """The parser is shared with the MSVC path; sanity-pin it against the
    common ``ns::class::method`` user-facing pattern."""

    def test_global_cpp_and_c_patterns_parse(self):
        with tempfile.NamedTemporaryFile('w', suffix='.map', delete=False) as f:
            f.write(_BASIC_EXPORT_MAP)
            map_path = f.name
        try:
            globals_, locals_ = builtin_tools._parse_export_map(map_path)
            cpp_pats = {p for (p, is_cpp, _) in globals_ if is_cpp}
            c_pats = {p for (p, is_cpp, _) in globals_ if not is_cpp}
            # The two C++ patterns inside extern "C++" land in cpp_pats; the
            # bare C identifier outside it lands in c_pats.
            self.assertIn('mylib::Api::*', cpp_pats)
            self.assertIn('mylib::Create', cpp_pats)
            self.assertIn('api_init', c_pats)
            # local: *; hides anything not explicitly exported.
            local_pats = [p for (p, _, _) in locals_]
            self.assertEqual(['*'], local_pats)
        finally:
            os.unlink(map_path)


class ExportMapKeepsTest(unittest.TestCase):
    """The shared keep-decision: a global wildcard wins over local *;
    anything else falls through to local."""

    def test_cpp_namespace_wildcard_keeps(self):
        globals_ = [('mylib::Api::*', True, False)]
        locals_ = [('*', False, False)]
        self.assertTrue(builtin_tools._export_map_keeps(
            '_ZN5mylib3Api5GreetEv', 'mylib::Api::Greet', globals_, locals_))

    def test_unmatched_cpp_falls_to_local_star_and_hides(self):
        globals_ = [('mylib::Api::*', True, False)]
        locals_ = [('*', False, False)]
        self.assertFalse(builtin_tools._export_map_keeps(
            '_ZN8internal4HelpEv', 'internal::Help', globals_, locals_))

    def test_c_identifier_matches_outside_extern_cpp(self):
        globals_ = [('api_init', False, False)]
        locals_ = [('*', False, False)]
        # name-only demangling of a C symbol just returns the symbol back.
        self.assertTrue(builtin_tools._export_map_keeps(
            'api_init', 'api_init', globals_, locals_))


class MacosObjGlobalSymbolsTest(unittest.TestCase):
    """The output parser must keep external+defined symbols and drop the
    noise (file headers in multi-arch builds, anything not in
    ``T/D/S/B/R``)."""

    def test_parses_nm_p_output(self):
        nm_output = (
            '_main T 0000000000000000 0\n'
            '_ZN5mylib3Api5GreetEv T 0000000000000050 0\n'
            '_g_state D 0000000000001000 8\n'
            # An undefined import would normally be filtered out by -U; keep
            # the test defensive against an nm build that doesn't drop them.
            '_external_thing U 0\n'
            '\n'  # blank lines must not crash the parser
        )
        with mock.patch.object(subprocess,
                               'check_output', return_value=nm_output):
            syms = builtin_tools._macos_obj_global_symbols('any.o')
        self.assertEqual(
            ['_main', '_ZN5mylib3Api5GreetEv', '_g_state'], syms)


class GenerateMacosExportsTest(unittest.TestCase):
    """End-to-end: feed objs (mocked nm) + map → assert the on-disk list."""

    def _setup(self, nm_lines, demangled_map):
        """Mock nm output and demangling so we don't need a real toolchain."""
        nm_output_per_obj = {
            'a.o': '\n'.join(nm_lines['a.o']) + '\n',
        }

        def fake_nm(cmd, **_kwargs):
            return nm_output_per_obj[cmd[-1]]

        def fake_demangle(stripped):
            # demangled_map: mangled-without-leading-underscore -> demangled
            return demangled_map.get(stripped)

        return mock.patch.object(subprocess,
                                 'check_output', side_effect=fake_nm), \
               mock.patch.object(builtin_tools, '_macos_cxa_demangle',
                                 side_effect=fake_demangle)

    def test_emits_only_matched_symbols_in_sorted_order(self):
        # Three C++ symbols + one C symbol; the export_map keeps only the
        # mylib::Api::Greet member and the C api_init entry-point.
        nm_lines = {'a.o': [
            '_ZN5mylib3Api5GreetEv T 0 0',
            '_ZN8internal4HelpEv T 0x10 0',
            '_ZN5mylib6CreateEv T 0x20 0',
            '_api_init T 0x30 0',
        ]}
        demangled = {
            'ZN5mylib3Api5GreetEv': 'mylib::Api::Greet()',
            'ZN8internal4HelpEv':   'internal::Help()',
            'ZN5mylib6CreateEv':    'mylib::Create()',
            # _api_init is a C symbol; demangle returns None -> raw name used.
            'api_init': None,
        }
        with tempfile.TemporaryDirectory() as td:
            map_path = os.path.join(td, 'api.map')
            with open(map_path, 'w') as f:
                f.write(_BASIC_EXPORT_MAP)
            out_path = os.path.join(td, 'libapi.dylib.exported_symbols_list')

            nm_patch, demangle_patch = self._setup(nm_lines, demangled)
            with nm_patch, demangle_patch:
                builtin_tools.generate_macos_exports(
                    [out_path, map_path, 'a.o'])

            with open(out_path) as f:
                body = f.read()

        self.assertIn('# Generated by Blade from api.map\n', body)
        symbols = [line for line in body.splitlines() if not line.startswith('#')]
        # ld64 expects the underscore-prefixed mangled names. Sorted so the
        # output is deterministic across runs.
        self.assertEqual(
            ['_ZN5mylib3Api5GreetEv', '_ZN5mylib6CreateEv', '_api_init'],
            symbols)


@unittest.skipUnless(sys.platform == 'darwin',
                     'libc++abi __cxa_demangle is only present on darwin')
class CxaDemangleSmokeTest(unittest.TestCase):
    """Smoke-test the real demangler so a future libc++abi rename can't
    silently fall back to raw symbols."""

    def setUp(self):
        # Force reload of the cached function pointer so this test is
        # independent of test-ordering.
        builtin_tools._macos_cxa_demangle_fn = None
        builtin_tools._macos_cxa_demangle_probed = False

    def test_demangles_simple_c_plus_plus_symbol(self):
        # `void mylib::Greet()` mangles to _ZN5mylib5GreetEv (no leading
        # underscore once we've stripped the Mach-O prefix).
        result = builtin_tools._macos_cxa_demangle('_ZN5mylib5GreetEv')
        self.assertEqual('mylib::Greet()', result)

    def test_returns_none_for_non_cpp(self):
        # Plain C identifier — __cxa_demangle should signal "not mangled".
        self.assertIsNone(builtin_tools._macos_cxa_demangle('api_init'))

    def test_name_only_drops_parameter_list(self):
        # The wrapper used by generate_macos_exports must lop off `()`
        # so name-only matching against `ns::class::method` patterns works.
        self.assertEqual('mylib::Greet',
                         builtin_tools._macos_demangle_name_only('_ZN5mylib5GreetEv'))


if __name__ == '__main__':
    unittest.main()
