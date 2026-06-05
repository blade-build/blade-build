#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for CcTarget._check_hdrs_existence (issue #886).

"""Tests for the generate-time validation that ``hdrs``/``srcs`` entries
either exist in the source tree or are declared as generated outputs by
some dep.

The check covers three "exists or declared" paths and one "real miss"
path; this file pins all four.
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402


def _bare_target(build_dir='build64_release'):
    """Build a CcTarget instance bypassing __init__.

    The check method only reads from ``self.attr`` (expanded_hdrs /
    expanded_srcs) and ``self.build_dir`` / ``self.data`` (where the
    cached transitive-generated map is stashed); side-stepping __init__
    keeps the test focused on the check itself.
    """
    t = cc_targets.CcTarget.__new__(cc_targets.CcTarget)
    t.attr = {}
    t.data = {}
    t.deps = []
    t.build_dir = build_dir
    t.errors = []
    t.error = t.errors.append
    return t


def _entry(src, full_path):
    """The (src, full_path) tuple shape produced by _expand_sources."""
    return (src, full_path)


class CheckHdrsExistenceTest(unittest.TestCase):
    """The three "covered" branches must skip silently; the fourth
    "missing" branch must raise an error with the BUILD-friendly hint."""

    def _check(self, target, declared_hdrs=None, declared_incs=None):
        """Run _check_hdrs_existence with patched dep-walking helper.

        ``_transitive_declared_output_files`` walks ``target.deps``; we
        short-circuit it so individual test cases just say what the
        ambient generated set is. The parameter name stays ``declared_hdrs``
        for caller clarity -- in the production code path the same set
        also includes ``gen_rule`` raw outputs (``.cc`` / ``.cpp``).
        """
        declared_hdrs = declared_hdrs or set()
        declared_incs = declared_incs or set()
        with mock.patch.object(cc_targets, '_transitive_declared_output_files',
                               return_value=(declared_hdrs, declared_incs)):
            target._check_hdrs_existence()
        return target.errors

    # ---- 3 covered paths: must NOT error ----

    def test_source_file_present_on_disk(self):
        """A hdr whose full_path is NOT under build_dir was found on disk
        by _expand_sources; the check skips it."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [_entry('logging.h',
                                          'flare/base/logging.h')]
        self.assertEqual(self._check(t), [])

    def test_assumed_generated_matches_declared_generated_hdrs(self):
        """The path was flipped to under build_dir because the file is
        missing, but a dep declared it as a `generated_hdrs` output."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [_entry('foo.pb.h',
                                          'build64_release/flare/proto/foo.pb.h')]
        errors = self._check(t, declared_hdrs={'flare/proto/foo.pb.h'})
        self.assertEqual(errors, [])

    def test_assumed_generated_under_declared_generated_incs(self):
        """The path is under a dir some dep declared as `generated_incs`
        (e.g. thrift's gen-cpp/), and the exact file isn't enumerated
        but is reachable via the include root."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [_entry('gen-cpp/MyService.h',
                                          'build64_release/svc/gen-cpp/MyService.h')]
        errors = self._check(t, declared_incs={'svc/gen-cpp'})
        self.assertEqual(errors, [])

    # ---- The missing-and-undeclared case: MUST error ----

    def test_typo_header_in_hdrs_errors(self):
        """The bug from #886: hdr listed in BUILD doesn't exist on disk
        AND no dep generates it. Must surface as a clear error."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [_entry('logging.hh',
                                          'build64_release/flare/base/logging.hh')]
        errors = self._check(t)
        self.assertEqual(len(errors), 1)
        self.assertIn('logging.hh', errors[0])
        self.assertIn('does not exist', errors[0])
        self.assertIn('mistype', errors[0])

    def test_typo_source_in_srcs_errors(self):
        """Same silent-flip exists for srcs entries; cover it too."""
        t = _bare_target()
        t.attr['expanded_srcs'] = [_entry('logging.ccc',
                                          'build64_release/flare/base/logging.ccc')]
        errors = self._check(t)
        self.assertEqual(len(errors), 1)
        self.assertIn('logging.ccc', errors[0])
        self.assertIn('source file', errors[0])

    def test_multiple_missing_reports_each(self):
        """Each missing file gets its own error so users can fix in one pass."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [
            _entry('a.h', 'build64_release/pkg/a.h'),
            _entry('b.h', 'build64_release/pkg/b.h'),
        ]
        errors = self._check(t)
        self.assertEqual(len(errors), 2)
        self.assertIn('a.h', errors[0])
        self.assertIn('b.h', errors[1])

    # ---- mixed / edge cases ----

    def test_mixed_present_and_missing(self):
        """A target with one OK hdr and one typo'd hdr surfaces only the typo."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [
            _entry('good.h', 'flare/base/good.h'),               # on disk
            _entry('typo.hh', 'build64_release/flare/base/typo.hh'),  # not declared
        ]
        errors = self._check(t)
        self.assertEqual(len(errors), 1)
        self.assertIn('typo.hh', errors[0])

    def test_hdrs_and_srcs_both_checked(self):
        """Mixed: a typo in srcs AND a typo in hdrs both reported."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [_entry('a.h', 'build64_release/p/a.h')]
        t.attr['expanded_srcs'] = [_entry('b.cc', 'build64_release/p/b.cc')]
        errors = self._check(t)
        self.assertEqual(len(errors), 2)
        # Order matters: hdrs first, then srcs
        self.assertIn('a.h', errors[0])
        self.assertIn('header file', errors[0])
        self.assertIn('b.cc', errors[1])
        self.assertIn('source file', errors[1])

    def test_empty_expanded_lists_no_error(self):
        """A target with no hdrs/srcs declared (legitimate: header-only
        wrapping `prebuilt_cc_library`) must not error."""
        t = _bare_target()
        # attr is empty; both .get() calls return []
        self.assertEqual(self._check(t), [])

    def test_gen_rule_outputs_cover_srcs(self):
        """Regression: a gen_rule produces a .cc which a downstream
        cc_library lists in `srcs=`. The .cc is in the gen_rule's
        `attr['outputs']` (not `generated_hdrs`, which filters to
        headers). The check must recognize it. See flare's
        `cc_flare_library` macro for the canonical pattern."""
        t = _bare_target()
        t.attr['expanded_srcs'] = [_entry('echo.flare.pb.cc',
                                          'build64_release/rpc/echo.flare.pb.cc')]
        # The wrapping cc_library deps on a gen_rule whose outputs include
        # this .cc; our _transitive_declared_output_files helper merges
        # outputs into the declared file set.
        errors = self._check(t, declared_hdrs={'rpc/echo.flare.pb.cc'})
        self.assertEqual(errors, [])

    def test_inc_prefix_match_not_substring(self):
        """``declared_incs='gen-cpp'`` must not match a file in ``gen-cpp-other/``.
        Guards against accidental substring/prefix-without-slash matching."""
        t = _bare_target()
        t.attr['expanded_hdrs'] = [_entry('gen-cpp-other/X.h',
                                          'build64_release/svc/gen-cpp-other/X.h')]
        errors = self._check(t, declared_incs={'svc/gen-cpp'})
        # X.h is NOT under svc/gen-cpp, despite the prefix string match
        self.assertEqual(len(errors), 1)
        self.assertIn('gen-cpp-other/X.h', errors[0])


if __name__ == '__main__':
    unittest.main()
