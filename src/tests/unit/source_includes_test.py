#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for inclusion_check._scan_source_includes and
_read_all_incstk_paths (issue #1171).

The scanner supplements `-H` depth-1 entries so checks see direct `#include`s
that the multiple-include-guard optimization silently elided. It returns both
quoted and angle forms; downstream callers intersect with the set of paths the
compiler actually traversed (`_read_all_incstk_paths`) to filter out system
headers and inactive `#if 0` includes.
"""

import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.inclusion_check import (  # noqa: E402
    _parse_msvc_hdr_level_line,
    _read_all_incstk_paths,
    _remove_build_dir_prefix,
    _scan_source_includes,
    path_under_dir,
)


class ScanSourceIncludesTest(unittest.TestCase):
    def _scan(self, content: str) -> 'set[str]':
        with tempfile.NamedTemporaryFile('w', suffix='.cc', delete=False) as f:
            f.write(content)
            path = f.name
        try:
            return _scan_source_includes(path)
        finally:
            os.unlink(path)

    def test_quoted_includes(self):
        self.assertEqual(
            self._scan('#include "a/b.h"\n#include "c/d.h"\n'),
            {'a/b.h', 'c/d.h'})

    def test_angle_includes_returned(self):
        # Angle form is returned too (project headers may be spelled `<...>`);
        # downstream filtering against actual-compiled-paths discards system
        # headers like <vector>.
        self.assertEqual(
            self._scan('#include <vector>\n#include <project/owner.h>\n'),
            {'vector', 'project/owner.h'})

    def test_line_comment_hides_include(self):
        # `// #include "..."` -- the line no longer starts with `#`, so the
        # `^\s*#` anchor naturally excludes it; no comment-stripping needed.
        self.assertEqual(
            self._scan('// #include "ignored.h"\n#include "real.h"\n'),
            {'real.h'})

    def test_block_comment_hides_include(self):
        self.assertEqual(
            self._scan('/* #include "ignored.h" */\n#include "real.h"\n'),
            {'real.h'})

    def test_multiline_block_comment(self):
        text = (
            '/*\n'
            ' * #include "a.h"\n'
            ' * #include "b.h"\n'
            ' */\n'
            '#include "real.h"\n'
        )
        self.assertEqual(self._scan(text), {'real.h'})

    def test_path_normalized(self):
        self.assertEqual(
            self._scan('#include "./pkg/./foo.h"\n#include "pkg//bar.h"\n'),
            {'pkg/foo.h', 'pkg/bar.h'})

    def test_indented_and_spaced(self):
        # Allow indentation and extra whitespace per the C preprocessor grammar.
        self.assertEqual(
            self._scan('   #  include    "a.h"\n#include\t"b.h"\n'),
            {'a.h', 'b.h'})

    def test_empty_file(self):
        self.assertEqual(self._scan(''), set())

    def test_no_includes(self):
        self.assertEqual(self._scan('int main(){return 0;}\n'), set())

    def test_macro_form_not_resolved(self):
        # Documented limitation: macro/computed includes are invisible to regex.
        # `-H` covers those (except when also guard-suppressed - the rare
        # intersection accepted in issue #1171).
        self.assertEqual(
            self._scan('#define MY_HDR "x.h"\n#include MY_HDR\n#include "y.h"\n'),
            {'y.h'})

    def test_missing_file_returns_empty(self):
        self.assertEqual(_scan_source_includes('/nonexistent/path/xyz.cc'), set())

    # --- design: scanner is intentionally naive, intersection is the gate

    def test_returns_includes_inside_if_zero_by_design(self):
        # Scanner is regex-only -- it returns includes regardless of any
        # surrounding `#if 0`, `#ifdef`, or untaken branch. Filtering happens
        # downstream by intersecting with `_read_all_incstk_paths` (paths the
        # compiler actually traversed). Documenting that contract here.
        text = (
            '#if 0\n#include "if_zero.h"\n#endif\n'
            '#ifdef NEVER_DEFINED\n#include "untaken.h"\n#endif\n'
            '#include "real.h"\n'
        )
        self.assertEqual(
            self._scan(text),
            {'if_zero.h', 'untaken.h', 'real.h'})


class ReadAllIncstkPathsTest(unittest.TestCase):
    def _write(self, content: str) -> str:
        f = tempfile.NamedTemporaryFile('w', suffix='.incstk', delete=False)
        f.write(content)
        f.close()
        return f.name

    def test_collects_paths_at_any_depth(self):
        path = self._write(
            '. ./pkg/a.h\n'
            '.. ./pkg/b.h\n'
            '... ./pkg/c.h\n'
        )
        try:
            self.assertEqual(
                _read_all_incstk_paths(path, 'build64_release'),
                {'pkg/a.h', 'pkg/b.h', 'pkg/c.h'})
        finally:
            os.unlink(path)

    def test_absolute_paths_filtered(self):
        # System headers from `-H` come as absolute paths; the wrapper's awk
        # usually drops them, but be defensive in case any leaks through.
        path = self._write(
            '. ./pkg/a.h\n'
            '.. /usr/include/stdio.h\n'
        )
        try:
            self.assertEqual(
                _read_all_incstk_paths(path, 'build64_release'),
                {'pkg/a.h'})
        finally:
            os.unlink(path)

    def test_build_dir_prefix_stripped(self):
        path = self._write(
            '. ./pkg/a.h\n'
            '.. build64_release/proto/x.pb.h\n'
        )
        try:
            self.assertEqual(
                _read_all_incstk_paths(path, 'build64_release'),
                {'pkg/a.h', 'proto/x.pb.h'})
        finally:
            os.unlink(path)

    def test_stops_at_first_non_inclusion_line(self):
        # `-H` output can be followed by other diagnostics; the wrapper's awk
        # generally cleans these up, but the reader should still terminate.
        path = self._write(
            '. ./pkg/a.h\n'
            'some other diagnostic line\n'
            '.. ./pkg/should_not_appear.h\n'
        )
        try:
            self.assertEqual(
                _read_all_incstk_paths(path, 'build64_release'),
                {'pkg/a.h'})
        finally:
            os.unlink(path)

    def test_missing_file_returns_empty(self):
        self.assertEqual(
            _read_all_incstk_paths('/nonexistent/path/xyz.incstk', 'build64_release'),
            set())

    # --- MSVC format paths ---

    @unittest.skipUnless(os.name == 'nt', 'MSVC format only used on Windows')
    def test_msvc_format_collects_paths(self):
        path = self._write(
            'Note: including file:  pkg/a.h\n'
            'Note: including file:    pkg/b.h\n'
        )
        try:
            self.assertEqual(
                _read_all_incstk_paths(path, 'build64_release'),
                {'pkg/a.h', 'pkg/b.h'})
        finally:
            os.unlink(path)

    @unittest.skipUnless(os.name == 'nt', 'MSVC format only used on Windows')
    def test_msvc_format_strips_build_dir_prefix(self):
        path = self._write(
            'Note: including file:  pkg/a.h\n'
            'Note: including file:    build64_release/proto/x.pb.h\n'
        )
        try:
            self.assertEqual(
                _read_all_incstk_paths(path, 'build64_release'),
                {'pkg/a.h', 'proto/x.pb.h'})
        finally:
            os.unlink(path)


class RemoveBuildDirPrefixTest(unittest.TestCase):
    def test_strips_prefix_with_forward_slash(self):
        self.assertEqual(
            _remove_build_dir_prefix('build64_release/pkg/a.h', 'build64_release'),
            'pkg/a.h')

    def test_no_prefix_match_returns_unchanged(self):
        self.assertEqual(
            _remove_build_dir_prefix('pkg/a.h', 'build64_release'),
            'pkg/a.h')

    def test_partial_prefix_not_stripped(self):
        # 'build64' is a substring but not the full dir component
        self.assertEqual(
            _remove_build_dir_prefix('build64/pkg/a.h', 'build64_release'),
            'build64/pkg/a.h')


class PathUnderDirTest(unittest.TestCase):
    def test_sub_path_matches_with_forward_slash(self):
        self.assertTrue(path_under_dir('pkg/sub/x.h', 'pkg'))

    def test_exact_dir_matches(self):
        self.assertTrue(path_under_dir('pkg', 'pkg'))

    def test_dot_matches_any(self):
        self.assertTrue(path_under_dir('anything.h', '.'))

    def test_non_sub_path_returns_false(self):
        self.assertFalse(path_under_dir('other/x.h', 'pkg'))

    def test_sibling_dir_prefix_returns_false(self):
        # 'pkg_extra' starts with 'pkg' but is not under 'pkg/'
        self.assertFalse(path_under_dir('pkg_extra/x.h', 'pkg'))


class ParseMsvcHdrLevelLineTest(unittest.TestCase):
    def test_basic_level(self):
        level, hdr = _parse_msvc_hdr_level_line(
            'Note: including file:  pkg/a.h')
        self.assertEqual(level, 2)
        self.assertEqual(hdr, 'pkg/a.h')

    def test_normalizes_backslash_to_forward(self):
        _, hdr = _parse_msvc_hdr_level_line(
            'Note: including file:  pkg\\sub\\a.h')
        self.assertEqual(hdr, 'pkg/sub/a.h')

    def test_deep_nesting(self):
        level, hdr = _parse_msvc_hdr_level_line(
            'Note: including file:          deep/nested.h')
        self.assertEqual(level, 10)
        self.assertEqual(hdr, 'deep/nested.h')


if __name__ == '__main__':
    unittest.main()
