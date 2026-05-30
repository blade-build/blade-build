#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
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
    _read_all_incstk_paths,
    _scan_source_includes,
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


if __name__ == '__main__':
    unittest.main()
