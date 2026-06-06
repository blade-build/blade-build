#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""The MSVC link/solink rules must route through the link wrapper and prepend
the MSVC + Windows SDK bin dirs to PATH.

blade invokes link.exe by absolute path, but link itself spawns helper tools by
name -- notably mt.exe (in the SDK bin, a different dir from link.exe) for
/MANIFEST:EMBED. Without those dirs on PATH link fails with LNK1158. The link
wrapper prepends them; these tests pin that the rules pass --prepend-path with
both bin dirs.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_rule_support  # noqa: E402

_MSVC_BIN = os.path.join('C:', os.sep, 'msvc', 'bin')
_SDK_BIN = os.path.join('C:', os.sep, 'sdk', 'bin')


class MsvcLinkToolPathTest(unittest.TestCase):
    def _rules(self):
        gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
        gen.build_accelerator = mock.Mock()
        gen.build_accelerator.get_cc_commands.return_value = (
            'cl', 'cl', os.path.join(_MSVC_BIN, 'link.exe'))
        tools = {
            'ld': os.path.join(_MSVC_BIN, 'link.exe'),
            'cc': os.path.join(_MSVC_BIN, 'cl.exe'),
            'as': os.path.join(_MSVC_BIN, 'ml64.exe'),
            'rc': os.path.join(_SDK_BIN, 'rc.exe'),
        }
        gen.build_toolchain = mock.Mock()
        gen.build_toolchain.tool = tools.get
        gen.build_toolchain.filter_cc_flags = lambda f, *a: list(f)
        gen.build_toolchain.get_system_lib_paths.return_value = []
        gen._msvc_link_wrapper_py = mock.Mock(return_value='link_wrapper.py')
        gen._builtin_command = lambda builder, args='': 'cmd'  # for cc_windef
        gen._add_line = mock.Mock()
        gen.generate_rule = mock.Mock()
        with mock.patch('blade.cc_rule_support.config') as cfg:
            cfg.get_section.side_effect = lambda n: {
                'msvc_config': {'linkflags': []}, 'cc_config': {'linkflags': []}}[n]
            gen._generate_windows_link_rules()
        return {c.kwargs['name']: c.kwargs['command']
                for c in gen.generate_rule.call_args_list}

    def test_link_rules_prepend_msvc_and_sdk_bin(self):
        rules = self._rules()
        for name in ('link', 'solink'):
            cmd = rules[name]
            self.assertIn('--prepend-path', cmd, name)
            self.assertIn('link_wrapper.py', cmd, name)   # routed through wrapper
            self.assertIn(_MSVC_BIN, cmd, name)            # cvtres etc.
            self.assertIn(_SDK_BIN, cmd, name)             # mt.exe


if __name__ == '__main__':
    unittest.main()
