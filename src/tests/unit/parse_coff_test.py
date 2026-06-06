#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Tests for builtin_tools._parse_coff, including the bigobj variant.

`cl /bigobj` emits objects in the ANON_OBJECT_HEADER_BIGOBJ format (different
header, 20-byte IMAGE_SYMBOL_EX records, 32-bit section numbers). blade's
auto-`.def` / check-undefined parse COFF directly, so the parser must accept
both layouts and return the same (symbols, section_selection) shape.
"""

import os
import struct
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.builtin_tools import _parse_coff  # noqa: E402

_EXTERNAL = 2   # IMAGE_SYM_CLASS_EXTERNAL
_STATIC = 3     # IMAGE_SYM_CLASS_STATIC
_FUNC_TYPE = 0x20


def _aux_section(selection):
    # IMAGE_AUX_SYMBOL[_EX] section definition: Selection at offset 14.
    aux = struct.pack('<IHHIHBBH', 0, 0, 0, 0, 1, selection, 0, 0)  # 18 bytes
    return aux + b'\x00' * 2  # pad to 20 for bigobj; truncated to 18 for normal


class ParseCoffTest(unittest.TestCase):
    def _normal_obj(self, selection):
        # IMAGE_FILE_HEADER (20 bytes), symtab @20, 3 symbols (18 bytes each).
        hdr = struct.pack('<HHIIIHH', 0x8664, 1, 0, 20, 3, 0, 0)
        s0 = b'.text\x00\x00\x00' + struct.pack('<IhHBB', 0, 1, 0, _STATIC, 1)
        aux = _aux_section(selection)[:18]
        s1 = b'func\x00\x00\x00\x00' + struct.pack('<IhHBB', 0, 1, _FUNC_TYPE, _EXTERNAL, 0)
        strtab = struct.pack('<I', 4)
        return hdr + s0 + aux + s1 + strtab

    def _bigobj(self, selection):
        # ANON_OBJECT_HEADER_BIGOBJ (56 bytes), symtab @56, 3 symbols (20 bytes).
        hdr = struct.pack('<HHHH', 0, 0xFFFF, 2, 0x8664)
        hdr += struct.pack('<I', 0) + b'\x00' * 16          # timestamp, classid
        hdr += struct.pack('<IIII', 0, 0, 0, 0)             # sizeofdata,flags,md size/off
        hdr += struct.pack('<III', 1, 56, 3)                # nsections, symtab, nsyms
        assert len(hdr) == 56
        s0 = b'.text\x00\x00\x00' + struct.pack('<IiHBB', 0, 1, 0, _STATIC, 1)
        aux = _aux_section(selection)
        s1 = b'func\x00\x00\x00\x00' + struct.pack('<IiHBB', 0, 1, _FUNC_TYPE, _EXTERNAL, 0)
        strtab = struct.pack('<I', 4)
        return hdr + s0 + aux + s1 + strtab

    def test_normal_coff(self):
        syms, sel = _parse_coff(self._normal_obj(selection=2))
        self.assertEqual(syms, [('func', _EXTERNAL, 1, _FUNC_TYPE)])
        self.assertEqual(sel, {1: 2})

    def test_bigobj_does_not_raise_and_parses(self):
        syms, sel = _parse_coff(self._bigobj(selection=2))
        self.assertEqual(syms, [('func', _EXTERNAL, 1, _FUNC_TYPE)])
        self.assertEqual(sel, {1: 2})

    def test_bigobj_parity_with_normal(self):
        # The two layouts must yield identical parsed results.
        for selection in (1, 2, 5, 6):
            self.assertEqual(_parse_coff(self._bigobj(selection)),
                             _parse_coff(self._normal_obj(selection)))


if __name__ == '__main__':
    unittest.main()
