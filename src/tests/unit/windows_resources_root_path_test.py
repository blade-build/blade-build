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
    def _make_target(self, target_path, deps=None, build_targets=None):
        t = wrt.WindowsResourcesTarget.__new__(wrt.WindowsResourcesTarget)
        t.path = target_path
        t.name = 'res'
        t.build_dir = 'build64_release'
        t.attr = {'rc_files': ['app.rc'], 'resources': [], 'hdrs': []}
        t.data = {}
        # expanded_deps is the direct + transitive dep list (set by the
        # dependency analyzer before generate()).
        t.expanded_deps = deps or []
        t.deps = deps or []
        t.blade = mock.Mock()
        t.blade.get_root_dir.return_value = os.path.join('C:', os.sep, 'ws', 'proj')
        t.blade.get_build_targets.return_value = build_targets or {}
        tc = t.blade.get_build_toolchain.return_value
        tc.tool.return_value = 'rc.exe'
        tc.get_system_include_paths.return_value = []
        t._source_file_path = lambda p: p
        t._target_file_path = lambda p: p
        t._add_target_file = mock.Mock()
        t.generate_build = mock.Mock()
        t._rules = []
        t._write_rule = lambda text: t._rules.append(text)
        return t

    def _run_generate(self, target_path):
        t = self._make_target(target_path)
        t.generate()
        return '\n'.join(t._rules)

    def test_root_package_has_no_escaped_quote(self):
        cmd = self._run_generate('')          # BUILD at repo root
        self.assertNotIn('\\"', cmd, 'trailing backslash escapes the rc /i quote')
        # the include dir is normpathed (no trailing separator before the quote)
        self.assertNotIn(os.sep + '"', cmd)

    def test_subdir_package_still_quoted(self):
        cmd = self._run_generate(os.path.join('sub', 'dir'))
        self.assertIn('rc.exe', cmd)
        self.assertNotIn('\\"', cmd)

    def test_generated_header_resolves_via_build_dir_not_its_own_dir(self):
        # A dep gen_rule produces a header the .rc #includes (e.g. licence.h),
        # here in a sub-build-dir. The build dir goes on rc /i (so the .rc
        # resolves it by build-dir-relative path), the header's OWN dir is NOT
        # auto-added (that risked shadowing a system header), and the file is an
        # implicit_dep so rc waits for it.
        hdr = os.path.join('build64_release', 'sub', 'licence.h')
        gen = mock.Mock()
        gen.attr = {'generated_hdrs': [hdr], 'generated_incs': []}
        t = self._make_target('', deps=['//:gen'], build_targets={'//:gen': gen})
        t.generate()
        cmd = '\n'.join(t._rules)
        self.assertIn('/i"build64_release"', cmd)                       # build dir on rc /i
        self.assertNotIn(os.path.join('build64_release', 'sub'), cmd)   # header's own dir NOT added
        self.assertIn(hdr, t.generate_build.call_args.kwargs.get('implicit_deps', []))

    def test_explicit_generated_inc_on_rc_path(self):
        # Explicit export_incs / generated_incs ARE added to rc /i (opt-in).
        inc = os.path.join('build64_release', 'pkg', 'inc')
        gen = mock.Mock()
        gen.attr = {'generated_hdrs': [], 'generated_incs': [inc]}
        t = self._make_target('', deps=['//:gen'], build_targets={'//:gen': gen})
        t.generate()
        self.assertIn(inc, '\n'.join(t._rules))

    def test_dep_generated_headers_uses_expanded_deps(self):
        # expanded_deps is already flattened (direct + transitive); the helper
        # returns generated-header FILES + only the explicit generated_incs dirs.
        leaf = mock.Mock()
        leaf.attr = {'generated_hdrs': [os.path.join('bd', 'a.h')], 'generated_incs': []}
        mid = mock.Mock()
        mid.attr = {'generated_hdrs': [], 'generated_incs': [os.path.join('bd', 'inc')]}
        t = self._make_target('', deps=['//:mid', '//:leaf'],
                              build_targets={'//:mid': mid, '//:leaf': leaf})
        files, inc_dirs = t._dep_generated_headers()
        self.assertEqual(files, {os.path.join('bd', 'a.h')})
        self.assertEqual(inc_dirs, {os.path.join('bd', 'inc')})  # only explicit generated_incs


if __name__ == '__main__':
    unittest.main()
