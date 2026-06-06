#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for the glob() exclude pattern matching, covering the
# globstar (**) behavior reported in issue #687.

"""Tests for blade.load_build_files._glob_full_match.

The bug from #687: ``glob(exclude=['**/...'])`` did not work because
``PurePath.match`` is a right-anchored partial match -- a trailing
``**`` only expands one path component. Modern Python's
``PurePath.full_match`` has the correct POSIX-globstar semantics but
only exists in 3.13+. Blade supports 3.10+, so we need a fallback that
behaves the same on every supported version.
"""

import os
import sys
import unittest
from pathlib import PurePath

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.load_build_files import _glob_full_match, _match_globstar  # noqa: E402


class GlobstarSemanticsTest(unittest.TestCase):
    """Pin the POSIX-globstar semantics of `**` in exclude patterns.

    Same behavior expected on every supported Python (3.10+), regardless
    of whether ``PurePath.full_match`` is available locally.
    """

    def _check(self, path, pattern, expected):
        actual = _glob_full_match(PurePath(path), pattern)
        self.assertEqual(actual, expected,
                         msg=f'match({path!r}, {pattern!r}) = {actual}, expected {expected}')

    # ---- the original bug: ** anywhere in the pattern ----

    def test_globstar_middle_one_level(self):
        # Original symptom from #687 -- one-level case used to work
        # accidentally via right-anchored partial match.
        self._check('b/sub/y.cc', '**/sub/**', True)

    def test_globstar_middle_deep(self):
        # The case that exposed the bug: ** at both ends with a deeply
        # nested path. PurePath.match returns False here.
        self._check('c/sub/deep/z.cc', '**/sub/**', True)

    def test_globstar_middle_at_top(self):
        # Bare directory just below repo root.
        self._check('sub/x.cc', '**/sub/**', True)

    def test_globstar_no_match_at_top(self):
        # No `sub` in path: must not match.
        self._check('top.cc', '**/sub/**', False)

    def test_globstar_no_match_sibling(self):
        # `sub` is part of a sibling but not on this path.
        self._check('a/notsub/x.cc', '**/sub/**', False)

    # ---- ** as zero-or-more components (POSIX globstar) ----

    def test_globstar_leading_matches_top_level(self):
        # `**/*.cc` should match top-level .cc too (** = zero components).
        # Python 3.13 full_match agrees; older PurePath.match returns False.
        self._check('top.cc', '**/*.cc', True)

    def test_globstar_leading_matches_nested(self):
        self._check('a/b/c.cc', '**/*.cc', True)

    def test_globstar_middle_zero_components(self):
        # `a/**/*.cc` matches `a/c.cc` (** = 0 components).
        self._check('a/c.cc', 'a/**/*.cc', True)

    def test_globstar_middle_multiple_components(self):
        self._check('a/b/c/d.cc', 'a/**/*.cc', True)

    def test_globstar_alone(self):
        # `**` alone matches anything.
        self._check('foo', '**', True)
        self._check('foo/bar', '**', True)
        self._check('foo/bar/baz/qux', '**', True)

    # ---- single * must not cross / ----

    def test_single_star_does_not_cross_slash(self):
        self._check('a.cc', '*.cc', True)
        self._check('a/b.cc', '*.cc', False)

    def test_anchored_star(self):
        self._check('a/b.cc', 'a/*.cc', True)
        self._check('a/b/c.cc', 'a/*.cc', False)
        self._check('a/b/c.cc', 'a/*/*.cc', True)

    # ---- ? matches single char, not / ----

    def test_question_mark_single_char(self):
        self._check('a.c', '?.c', True)
        self._check('ab.c', '?.c', False)
        self._check('a/c', '?', False)

    # ---- character class ----

    def test_character_class(self):
        self._check('a.cc', '[abc].cc', True)
        self._check('d.cc', '[abc].cc', False)

    # ---- exact match (no special chars) ----

    def test_literal_match(self):
        self._check('foo/bar', 'foo/bar', True)
        self._check('foo/baz', 'foo/bar', False)

    # ---- empty edge cases ----

    def test_pattern_only_globstar_matches_root(self):
        # An empty-ish path. PurePath('') is '.', which split('/') = ['.'].
        # `**` is zero-or-more, including zero, so '.' counts as a single
        # component path that matches '**'.
        self._check('.', '**', True)

    # ---- consistency with full_match (when available) ----

    def test_consistency_with_native_full_match(self):
        """When Python provides PurePath.full_match (3.13+), our fallback
        must agree with it on every test case above."""
        if not hasattr(PurePath, 'full_match'):
            self.skipTest('full_match not available on this Python')

        cases = [
            ('b/sub/y.cc', '**/sub/**'),
            ('c/sub/deep/z.cc', '**/sub/**'),
            ('top.cc', '**/sub/**'),
            ('a/b/c.cc', '**/*.cc'),
            ('top.cc', '**/*.cc'),
            ('a/c.cc', 'a/**/*.cc'),
            ('a/b/c/d.cc', 'a/**/*.cc'),
            ('a/b.cc', 'a/*.cc'),
            ('a/b/c.cc', 'a/*.cc'),
            ('a.cc', '*.cc'),
            ('a/b.cc', '*.cc'),
            ('foo', '**'),
            ('foo/bar/baz', '**'),
        ]
        for path, pattern in cases:
            native = PurePath(path).full_match(pattern)  # pyright: ignore[reportAttributeAccessIssue]
            ours = _match_globstar(path.split('/'), pattern.split('/'))
            self.assertEqual(ours, native,
                             msg=f'{path!r} vs {pattern!r}: ours={ours} native={native}')


class GlobExclusionIntegrationTest(unittest.TestCase):
    """Smoke test against the full glob() function with a temp directory.

    Covers the exact user-facing scenario from #687: include a tree,
    exclude paths under any directory matching `**/sub/**`.
    """

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _touch(self, relpath):
        full = os.path.join(self._tmpdir, relpath)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, 'w', encoding='utf-8').close()

    def test_exclude_globstar_in_middle(self):
        """The exact reproducer from #687.

        Files at multiple depths under `sub/` directories; exclude pattern
        `**/sub/**` must drop all of them.
        """
        from blade.load_build_files import _glob_full_match
        for f in ('top.cc',
                  'a/x.cc',
                  'b/sub/y.cc',           # 1 dir between sub and file
                  'c/sub/deep/z.cc',      # 2 dirs (used to be missed)
                  'd/sub/very/deep/w.cc', # 3 dirs
                  'e/notsub/q.cc'):
            self._touch(f)

        all_cc = []
        for root, _, files in os.walk(self._tmpdir):
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), self._tmpdir)
                all_cc.append(rel.replace(os.sep, '/'))

        excluded = sorted(p for p in all_cc
                          if _glob_full_match(PurePath(p), '**/sub/**'))
        kept = sorted(p for p in all_cc
                      if not _glob_full_match(PurePath(p), '**/sub/**'))

        self.assertEqual(excluded, ['b/sub/y.cc',
                                    'c/sub/deep/z.cc',
                                    'd/sub/very/deep/w.cc'])
        self.assertEqual(kept, ['a/x.cc', 'e/notsub/q.cc', 'top.cc'])


if __name__ == '__main__':
    unittest.main()
