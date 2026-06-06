#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Pins MSVC default-flag wiring: CRT per build profile, debug info, and the
matching linker flags.

Previously the CRT was hard-coded to /MD (so -p debug got the release CRT) and
the MSVC debug-info level was unwired (no /Z7, no PDB ever). These tests pin the
corrected behavior.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_rule_support  # noqa: E402


def _compile_rules(profile='release', debug_info='mid', cppflags=None, cxxflags=None):
    gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
    gen.build_toolchain = mock.Mock()
    gen.build_toolchain.filter_cc_flags = lambda flags, *a: list(flags)
    gen.build_toolchain.get_system_include_paths.return_value = []
    gen.build_accelerator = mock.Mock()
    gen.options = mock.Mock()
    gen.options.profile = profile
    gen.build_dir = 'build64_%s' % profile
    gen._msvc_tee_wrapper_py = mock.Mock(return_value='cc_wrapper.py')
    gen.generate_rule = mock.Mock()
    section = {
        'msvc_config': {'cppflags': cppflags or [], 'cflags': [],
                        'cxxflags': cxxflags or [],
                        'optimize': {'debug': ['/Od'], 'release': ['/O2']},
                        'debug_info_levels': {'no': [], 'mid': ['/Z7']}},
        'cc_config': {'cflags': [], 'cxxflags': [], 'cppflags': [], 'extra_incs': []},
        'global_config': {'debug_info_level': debug_info},
    }
    with mock.patch('blade.cc_rule_support.config') as cfg:
        cfg.get_section.side_effect = lambda n: section[n]
        gen._generate_windows_cc_compile_rules('cl.exe', 'cl.exe')
    return {c.kwargs['name']: c.kwargs['command']
            for c in gen.generate_rule.call_args_list}


def _link_flags(profile='release', debug_info='mid'):
    gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
    gen.build_accelerator = mock.Mock()
    gen.build_accelerator.get_cc_commands.return_value = ('cl', 'cl', 'link.exe')
    gen.build_toolchain = mock.Mock()
    gen.build_toolchain.tool = lambda k: None
    gen.build_toolchain.filter_cc_flags = lambda f, *a: list(f)
    gen.build_toolchain.get_system_lib_paths.return_value = []
    gen._msvc_link_wrapper_py = mock.Mock(return_value='lw.py')
    gen._builtin_command = lambda b, args='': 'cmd'
    captured = []
    gen._add_line = captured.append
    gen.generate_rule = mock.Mock()
    gen.options = mock.Mock()
    gen.options.profile = profile
    section = {'msvc_config': {'linkflags': []}, 'cc_config': {'linkflags': []},
               'global_config': {'debug_info_level': debug_info}}
    with mock.patch('blade.cc_rule_support.config') as cfg:
        cfg.get_section.side_effect = lambda n: section[n]
        gen._generate_windows_link_rules()
    return next(s for s in captured if s.startswith('linkflags = '))


class MsvcDefaultFlagsTest(unittest.TestCase):
    def test_release_uses_md(self):
        cc = _compile_rules(profile='release')['cc']
        self.assertIn('/MD', cc)
        self.assertNotIn('/MDd', cc)

    def test_debug_uses_mdd(self):
        self.assertIn('/MDd', _compile_rules(profile='debug')['cc'])

    def test_crt_not_double_added_when_user_pins_one(self):
        cc = _compile_rules(profile='release', cppflags=['/MT'])['cc']
        self.assertIn('/MT', cc)
        self.assertNotIn('/MD', cc)   # auto-CRT skipped because user pinned /MT

    def test_debug_info_z7_threaded(self):
        rules = _compile_rules(debug_info='mid')
        for name in ('cc', 'cxx'):
            self.assertIn('/Z7', rules[name])

    def test_debug_info_none_omits_z7(self):
        self.assertNotIn('/Z7', _compile_rules(debug_info='no')['cc'])

    def test_link_release_debug_and_opt(self):
        line = _link_flags(profile='release', debug_info='mid')
        for flag in ('/DEBUG', '/OPT:REF', '/OPT:ICF', '/INCREMENTAL:NO'):
            self.assertIn(flag, line)

    def test_link_debug_has_debug_no_opt(self):
        line = _link_flags(profile='debug', debug_info='mid')
        self.assertIn('/DEBUG', line)
        self.assertNotIn('/OPT:REF', line)

    def test_link_no_debug_info_omits_debug(self):
        self.assertNotIn('/DEBUG', _link_flags(profile='debug', debug_info='no'))


if __name__ == '__main__':
    unittest.main()
