#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Tests for the MSVC assembler (ml64/ml) rule and .asm routing.

cl.exe cannot assemble MASM; .asm sources must go through the toolchain's 'as'
tool (ml64.exe / ml.exe). These pin both halves: the 'as' rule is emitted and
runs that tool, and _get_rule_from_suffix routes .asm there on MSVC only.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_rule_support  # noqa: E402
from blade.cc_targets import CcLibrary  # noqa: E402


class MsvcAsmRuleTest(unittest.TestCase):
    def _gen(self, asm_tool: 'str | None' = 'ml64.exe'):
        gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
        gen.build_toolchain = mock.Mock()
        gen.build_toolchain.tool.return_value = asm_tool
        gen.generate_rule = mock.Mock()
        return gen

    def test_asm_rule_runs_ml64(self):
        gen = self._gen('ml64.exe')
        gen._generate_windows_asm_rule()
        self.assertTrue(gen.generate_rule.called)
        kw = gen.generate_rule.call_args.kwargs
        self.assertEqual('as', kw['name'])
        for tok in ('ml64.exe', '/c', '/Fo${out}', '${includes}', '${in}'):
            self.assertIn(tok, kw['command'])

    def test_no_rule_when_assembler_absent(self):
        gen = self._gen(None)
        gen._generate_windows_asm_rule()
        self.assertFalse(gen.generate_rule.called)


class AsmRoutingTest(unittest.TestCase):
    def _target(self, vendor):
        t = CcLibrary.__new__(CcLibrary)
        tc = mock.Mock()
        tc.cc_is = lambda v: v == vendor
        t.blade = mock.Mock()
        t.blade.get_build_toolchain.return_value = tc
        return t

    def test_asm_routed_to_as_on_msvc(self):
        t = self._target('msvc')
        self.assertEqual('as', t._get_rule_from_suffix('foo.asm', False))
        self.assertEqual('cxx', t._get_rule_from_suffix('foo.cpp', False))
        self.assertEqual('cc', t._get_rule_from_suffix('foo.c', False))

    def test_asm_not_routed_on_gcc(self):
        t = self._target('gcc')
        # GCC assembles .s/.S via the cc driver; .asm has no special routing.
        self.assertEqual('cc', t._get_rule_from_suffix('foo.asm', False))


if __name__ == '__main__':
    unittest.main()
