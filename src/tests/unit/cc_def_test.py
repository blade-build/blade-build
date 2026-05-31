#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the Windows DLL auto-export symbol filter.

`builtin_tools._select_dll_exports` turns parsed COFF symbol records into the
export list a `.def` needs. It must export only **external, defined** symbols,
and must drop *dedup* COMDAT symbols (templates / inlines / constants —
selection ANY/SAME_SIZE/EXACT_MATCH/LARGEST) while keeping NODUPLICATES
sections (ordinary functions under /Gy). These tests pin that logic with
synthetic records so they run on any platform (the COFF byte parser is
exercised separately, on real objects, on Windows).
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import builtin_tools  # noqa: E402  (sys.path tweak above)

_EXTERNAL = builtin_tools._IMAGE_SYM_CLASS_EXTERNAL
_STATIC = builtin_tools._IMAGE_SYM_CLASS_STATIC
_FUNC = builtin_tools._IMAGE_SYM_DTYPE_FUNCTION  # 0x20
_DATA = 0


class SelectDllExportsTest(unittest.TestCase):
    def test_external_defined_function_and_data_exported(self):
        symbols = [
            ('?Greet@@YAXXZ', _EXTERNAL, 3, _FUNC),
            ('?g_count@@3HA', _EXTERNAL, 4, _DATA),
        ]
        exports = dict(builtin_tools._select_dll_exports(symbols, {}))
        self.assertIn('?Greet@@YAXXZ', exports)
        self.assertFalse(exports['?Greet@@YAXXZ'])   # function → not DATA
        self.assertTrue(exports['?g_count@@3HA'])     # data → DATA

    def test_undefined_and_static_skipped(self):
        symbols = [
            ('?imported@@YAXXZ', _EXTERNAL, 0, _FUNC),   # section 0 → undefined import
            ('?local@@YAXXZ', _STATIC, 3, _FUNC),        # not external
        ]
        self.assertEqual([], builtin_tools._select_dll_exports(symbols, {}))

    def test_gy_noduplicates_kept_but_dedup_comdat_skipped(self):
        # Under /Gy a real function lands in its own COMDAT with selection
        # NODUPLICATES(1) — keep it. Template/inline copies use ANY(2) etc. —
        # drop them (the consumer instantiates its own from headers).
        symbols = [
            ('?Greet@@YAXXZ', _EXTERNAL, 11, _FUNC),                 # /Gy real fn
            ('??$tmpl@H@@YAXXZ', _EXTERNAL, 12, _FUNC),              # template ANY
            ('??_C@_05@strlit', _EXTERNAL, 13, _DATA),               # string literal ANY
            ('?big@@3HA', _EXTERNAL, 14, _DATA),                     # LARGEST
        ]
        selection = {11: 1, 12: 2, 13: 2, 14: 6}
        names = [n for n, _ in builtin_tools._select_dll_exports(symbols, selection)]
        self.assertEqual(['?Greet@@YAXXZ'], names)

    def test_dedup_preserves_first_seen(self):
        symbols = [
            ('?f@@YAXXZ', _EXTERNAL, 3, _FUNC),
            ('?f@@YAXXZ', _EXTERNAL, 9, _FUNC),  # same symbol from another object
        ]
        self.assertEqual(
            ['?f@@YAXXZ'],
            [n for n, _ in builtin_tools._select_dll_exports(symbols, {})])


_API_MAP = '''\
{
global:
    extern "C++" {
        # exported literally (signature stripped on MSVC)
        "mylib::Create()";
        mylib::Api::*;   /* every member */
    };
local:
    *;
};
'''


class ExportMapParseTest(unittest.TestCase):
    def _parse(self, text):
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.map', delete=False) as f:
            f.write(text)
            path = f.name
        try:
            return builtin_tools._parse_export_map(path)
        finally:
            os.unlink(path)

    def test_extern_cpp_quoted_and_glob_with_comments(self):
        globals_, locals_ = self._parse(_API_MAP)
        self.assertEqual(
            [('mylib::Create()', True, True), ('mylib::Api::*', True, False)],
            globals_)
        self.assertEqual([('*', False, False)], locals_)

    def test_top_level_pattern_is_not_cpp(self):
        globals_, _ = self._parse('{ global: my_c_func; local: *; };')
        self.assertEqual([('my_c_func', False, False)], globals_)

    def test_extern_c_block_is_not_cpp(self):
        globals_, _ = self._parse(
            '{ global: extern "C" { c_api; }; local: *; };')
        self.assertEqual([('c_api', False, False)], globals_)

    def test_global_before_and_after_extern_block(self):
        # A top-level pattern, then an extern "C++" block, then another
        # top-level pattern -- cpp must toggle on entry and back off on exit.
        globals_, _ = self._parse(
            '{ global: top1; extern "C++" { ns::*; }; top2; local: *; };')
        self.assertEqual(
            [('top1', False, False), ('ns::*', True, False), ('top2', False, False)],
            globals_)

    def test_named_version_nodes_are_flattened(self):
        # The node names (VER_1, VER_2) and the `} VER_1;` dependency must not
        # be read as patterns; their global/local lists are unioned.
        globals_, locals_ = self._parse(
            'VER_1 { global: a; local: la; };\n'
            'VER_2 { global: b; local: *; } VER_1;\n')
        self.assertEqual([('a', False, False), ('b', False, False)], globals_)
        self.assertEqual([('la', False, False), ('*', False, False)], locals_)

    def test_line_comment_and_only_global(self):
        globals_, locals_ = self._parse(
            '{\n'
            '  global:\n'
            '    keep_me;  // keep this one\n'
            '}; // no local section\n')
        self.assertEqual([('keep_me', False, False)], globals_)
        self.assertEqual([], locals_)

    def test_specific_local_patterns(self):
        _, locals_ = self._parse('{ local: secret_*; _internal; };')
        self.assertEqual(
            [('secret_*', False, False), ('_internal', False, False)], locals_)


class ExportMapKeepsTest(unittest.TestCase):
    def setUp(self):
        self.globals_ = [('mylib::Create()', True, True), ('mylib::Api::*', True, False)]
        self.locals_ = [('*', False, False)]

    def _keeps(self, name, dname):
        return builtin_tools._export_map_keeps(name, dname, self.globals_, self.locals_)

    def test_glob_matches_member(self):
        self.assertTrue(self._keeps('?Greet@Api@mylib@@QEBA...', 'mylib::Api::Greet'))

    def test_quoted_matches_by_name_part(self):
        # name-only demangling drops the "()" -> match the pattern's name part
        self.assertTrue(self._keeps('?Create@mylib@@YAPEAVApi@1@XZ', 'mylib::Create'))

    def test_unlisted_symbol_hidden_by_local_star(self):
        self.assertFalse(self._keeps('?Decorate@mylib@@YA...', 'mylib::Decorate'))

    def test_no_local_section_does_not_restrict(self):
        keeps = builtin_tools._export_map_keeps(
            'bar', 'bar', [('foo*', False, False)], [])
        self.assertTrue(keeps)  # global-only version node hides nothing

    def test_top_level_pattern_matches_raw_name(self):
        keeps = builtin_tools._export_map_keeps(
            'my_c_func', 'my_c_func', [('my_c_func', False, False)], [('*', False, False)])
        self.assertTrue(keeps)


if __name__ == '__main__':
    unittest.main()
