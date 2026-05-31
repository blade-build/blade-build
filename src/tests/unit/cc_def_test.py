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


if __name__ == '__main__':
    unittest.main()
