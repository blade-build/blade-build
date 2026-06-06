#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Regression test for windows_resources at the repo root.

For a BUILD at the workspace root, target.path is '', so
os.path.join(root, path) yields '<root>/' (trailing separator). Quoted into the
rc.exe command as /i"<root>\\" that backslash-escapes the closing quote and
rc.exe fails with RC1107. The rule must normpath the dir so no trailing
separator leaks into the quoted include flag.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import windows_resources_target as wrt  # noqa: E402


class WindowsResourcesRootPathTest(unittest.TestCase):
    def _run_generate(self, target_path):
        t = wrt.WindowsResourcesTarget.__new__(wrt.WindowsResourcesTarget)
        t.path = target_path
        t.name = 'res'
        t.attr = {'rc_files': ['app.rc'], 'resources': [], 'hdrs': []}
        t.data = {}
        t.blade = mock.Mock()
        t.blade.get_root_dir.return_value = os.path.join('C:', os.sep, 'ws', 'proj')
        tc = t.blade.get_build_toolchain.return_value
        tc.tool.return_value = 'rc.exe'
        tc.get_system_include_paths.return_value = []
        t._source_file_path = lambda p: p
        t._target_file_path = lambda p: p
        t._add_target_file = mock.Mock()
        t.generate_build = mock.Mock()
        rules = []
        t._write_rule = lambda text: rules.append(text)
        t.generate()
        return '\n'.join(rules)

    def test_root_package_has_no_escaped_quote(self):
        cmd = self._run_generate('')          # BUILD at repo root
        self.assertNotIn('\\"', cmd, 'trailing backslash escapes the rc /i quote')
        # the include dir is normpathed (no trailing separator before the quote)
        self.assertNotIn(os.sep + '"', cmd)

    def test_subdir_package_still_quoted(self):
        cmd = self._run_generate(os.path.join('sub', 'dir'))
        self.assertIn('rc.exe', cmd)
        self.assertNotIn('\\"', cmd)


if __name__ == '__main__':
    unittest.main()
