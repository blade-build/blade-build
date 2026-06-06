#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Tests for gen_rule per-platform command selection and wrapping (issue #1204).

gen_rule used a POSIX-only scaffold (`... && cd <dir> && ls ${out} > /dev/null`)
that broke on Windows cmd.exe. Now it picks cmd_bat / cmd_bash / cmd per
platform and wraps with the right interpreter + a portable output-existence
check. These tests pin that logic and that the old POSIX scaffold is gone.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import gen_rule_target as grt  # noqa: E402
from blade.gen_rule_target import GenRuleTarget  # noqa: E402


class GenRuleSelectTest(unittest.TestCase):
    def _select(self, cmd, cmd_bash, cmd_bat, osname, bash):
        with mock.patch.object(grt.os, 'name', osname), \
             mock.patch.object(grt.shutil, 'which', return_value=bash):
            return GenRuleTarget._select_command(cmd, cmd_bash, cmd_bat)

    def test_windows_prefers_bat(self):
        self.assertEqual(self._select('c', 'cb', 'bat', 'nt', 'bash')[:2], ('bat', 'bat'))

    def test_windows_bash_when_no_bat_and_bash_available(self):
        self.assertEqual(self._select('c', 'cb', '', 'nt', 'bash')[:2], ('cb', 'bash'))

    def test_windows_falls_back_to_cmd_without_bash(self):
        self.assertEqual(self._select('c', 'cb', '', 'nt', None)[:2], ('c', 'raw'))

    def test_windows_cmd_bash_raw_when_no_cmd_no_bash(self):
        self.assertEqual(self._select('', 'cb', '', 'nt', None)[:2], ('cb', 'raw'))

    def test_posix_prefers_bash(self):
        self.assertEqual(self._select('c', 'cb', '', 'posix', '/bin/bash')[:2], ('cb', 'bash'))

    def test_posix_falls_back_to_cmd_without_bash(self):
        self.assertEqual(self._select('c', 'cb', '', 'posix', None)[:2], ('c', 'raw'))

    def test_none_usable(self):
        self.assertIsNone(self._select('', '', '', 'posix', '/bin/bash')[0])
        # cmd_bat is ignored on POSIX
        self.assertIsNone(self._select('', '', 'bat', 'posix', '/bin/bash')[0])


class GenRuleWrapTest(unittest.TestCase):
    def _wrap(self, kind, osname, cmd='do_it'):
        t = GenRuleTarget.__new__(GenRuleTarget)
        t._gen_kind = kind
        t._bash = '/usr/bin/bash'
        t.attr = {'outputs': ['build/o1', 'build/o2']}
        # get_root_dir='' so os.path.join leaves the relative paths unchanged
        t.blade = mock.Mock()
        t.blade.get_root_dir.return_value = ''
        with mock.patch.object(grt.os, 'name', osname):
            return t._wrap_command(cmd)

    def _no_posix_scaffold(self, w):
        self.assertNotIn('/dev/null', w)
        self.assertNotIn(' ls ', w)

    def test_bash_kind(self):
        w = self._wrap('bash', 'posix')
        self.assertIn('/usr/bin/bash', w)
        self.assertIn('-c', w)
        self.assertIn('set -e -o pipefail', w)
        self.assertIn('test -e "build/o1"', w)
        self._no_posix_scaffold(w)

    def test_bat_kind(self):
        w = self._wrap('bat', 'nt')
        self.assertIn('cmd /S /E:ON /V:ON /D /c', w)
        self.assertIn('if not exist "build/o1" exit /b 1', w)
        self._no_posix_scaffold(w)

    def test_raw_windows_is_wrapped_in_cmd(self):
        w = self._wrap('raw', 'nt')
        self.assertIn('cmd /S /E:ON /V:ON /D /c', w)
        self.assertIn('if not exist', w)
        self._no_posix_scaffold(w)

    def test_raw_posix_is_plain_sh(self):
        w = self._wrap('raw', 'posix')
        self.assertNotIn('cmd /', w)
        self.assertIn('do_it && test -e "build/o1"', w)
        self._no_posix_scaffold(w)


class GenRuleExpandTest(unittest.TestCase):
    """$OUTS[i|name] / $SRCS[i|name] indexed/named references."""

    def _target(self, cmd, kind='raw', outputs=None, inputs=None):
        t = GenRuleTarget.__new__(GenRuleTarget)
        t.error = mock.Mock()
        t._gen_kind = kind
        t.path = 'pkg'
        t.build_dir = 'bd'
        t.srcs = ['in.y']
        t._expand_srcs = lambda: (inputs if inputs is not None else ['pkg/in.y'])
        t.attr = {
            'cmd': cmd,
            'outs': ['parser.cc', 'parser.h'],
            'outputs': outputs if outputs is not None
                       else ['bd/pkg/parser.cc', 'bd/pkg/parser.h'],
            'locations': [],
        }
        return t

    def test_index_ref_helper(self):
        t = self._target('')
        names, paths = ['a.cc', 'b.h'], ['o/a.cc', 'o/b.h']
        self.assertEqual(t._index_ref('0', names, paths, 'outs'), 'o/a.cc')
        self.assertEqual(t._index_ref('1', names, paths, 'outs'), 'o/b.h')
        self.assertEqual(t._index_ref('b.h', names, paths, 'outs'), 'o/b.h')
        t._index_ref('9', names, paths, 'outs')   # out of range
        t._index_ref('nope', names, paths, 'outs')  # unknown name
        self.assertEqual(t.error.call_count, 2)

    def test_outs_index_and_name(self):
        t = self._target('gen $OUTS[0] --hdr=$OUTS[parser.h]')
        self.assertEqual(t._expand_command(),
                         'gen bd/pkg/parser.cc --hdr=bd/pkg/parser.h')

    def test_srcs_index(self):
        t = self._target('use $SRCS[0]')
        self.assertEqual(t._expand_command(), 'use pkg/in.y')

    def test_bare_vars_still_expand(self):
        # $OUTS (no bracket) must still become ${out}, not be eaten by indexing
        t = self._target('all $OUTS first $FIRST_OUT')
        self.assertEqual(t._expand_command(), 'all ${out} first ${_out_1}')

    def test_index_does_not_clobber_bare_outs(self):
        t = self._target('$OUTS[0] then $OUTS')
        self.assertEqual(t._expand_command(), 'bd/pkg/parser.cc then ${out}')

    def test_bash_kind_forward_slashes_and_concrete_paths(self):
        # bash kind: backslash -> '/', and $OUTS/$SRCS are concrete (not ${out})
        t = self._target(
            'gen $OUTS[0] all $OUTS in $SRCS',
            kind='bash',
            outputs=[r'bd\pkg\parser.cc', r'bd\pkg\parser.h'],
            inputs=[r'pkg\in.y'])
        out = t._expand_command()
        self.assertEqual(out, 'gen bd/pkg/parser.cc all bd/pkg/parser.cc bd/pkg/parser.h in pkg/in.y')
        self.assertNotIn('\\', out)
        self.assertNotIn('${out}', out)


if __name__ == '__main__':
    unittest.main()
