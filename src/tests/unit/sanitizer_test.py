#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for sanitizer support (#1038, ASan phase).

Covers the sanitizer helper (parse/canonicalize/tag/toolchain check), the
build-dir variant tag, and the per-target `sanitize=False` opt-out flag.
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import sanitizer  # noqa: E402
from blade.workspace import _build_variant_suffix  # noqa: E402


class _Opts:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class SanitizerHelperTest(unittest.TestCase):
    def test_parse_canonicalizes_aliases_and_dedups(self):
        self.assertEqual(['address'], sanitizer.parse('asan'))
        self.assertEqual(['address'], sanitizer.parse('address'))
        self.assertEqual(['address'], sanitizer.parse('asan,address'))  # dedup
        self.assertEqual([], sanitizer.parse(''))
        self.assertEqual([], sanitizer.parse(None))

    def test_flag_and_tag(self):
        s = sanitizer.parse('address')
        self.assertEqual('address', sanitizer.fsanitize_value(s))
        self.assertEqual('asan', sanitizer.build_tag(s))

    def test_more_sanitizer_aliases(self):
        self.assertEqual(['undefined'], sanitizer.parse('ubsan'))
        self.assertEqual(['undefined'], sanitizer.parse('undefined'))
        self.assertEqual(['leak'], sanitizer.parse('lsan'))

    def test_set_is_canonical_sorted(self):
        # Order-independent: both spellings -> the same sorted set + tag.
        self.assertEqual(['address', 'undefined'], sanitizer.parse('ubsan,address'))
        self.assertEqual(['address', 'undefined'], sanitizer.parse('address,undefined'))
        self.assertEqual('asan+ubsan',
                         sanitizer.build_tag(['address', 'undefined']))

    def test_compile_flags_make_ubsan_fatal(self):
        flags = sanitizer.compile_flags(['address', 'undefined'])
        self.assertIn('-fsanitize=address,undefined', flags)
        self.assertIn('-fno-omit-frame-pointer', flags)
        self.assertIn('-fno-sanitize-recover=undefined', flags)
        # No UBSan -> no recover flag.
        self.assertNotIn('-fno-sanitize-recover=undefined',
                         sanitizer.compile_flags(['address']))

    def test_link_flags(self):
        self.assertEqual(['-fsanitize=address,leak'],
                         sanitizer.link_flags(['address', 'leak']))

    def test_unknown_is_fatal(self):
        # console.fatal raises SystemExit.
        with self.assertRaises(SystemExit):
            sanitizer.parse('bogus')

    def test_check_toolchain_rejects_msvc(self):
        msvc = mock.Mock()
        msvc.cc_is.side_effect = lambda v: v == 'msvc'
        with self.assertRaises(SystemExit):
            sanitizer.check_toolchain(['address'], msvc)
        # No sanitizer -> no check, no error.
        sanitizer.check_toolchain([], msvc)


class BuildVariantSuffixSanitizerTest(unittest.TestCase):
    def test_sanitizer_tag_in_build_dir(self):
        self.assertEqual('_asan',
                         _build_variant_suffix(_Opts(sanitizers=['address'])))

    def test_off_is_empty(self):
        self.assertEqual('', _build_variant_suffix(_Opts(sanitizers=[])))
        self.assertEqual('', _build_variant_suffix(_Opts()))

    def test_composes_with_coverage(self):
        self.assertEqual(
            '_coverage_asan',
            _build_variant_suffix(_Opts(coverage=True, sanitizers=['address'])))


class PerTargetOptOutTest(unittest.TestCase):
    """`sanitize=False` adds -fno-sanitize for that target's compiles."""

    def _cc_target(self, sanitize, sanitizers):
        from blade import cc_targets
        target = cc_targets.CcTarget.__new__(cc_targets.CcTarget)
        target.attr = {'defs': [], 'extra_cppflags': [], 'sanitize': sanitize}
        target.blade = mock.Mock()
        target.blade.get_options.return_value = _Opts(sanitizers=sanitizers)
        target._get_incs_list = mock.Mock(return_value=([], []))
        return target

    def test_optout_drops_instrumentation(self):
        target = self._cc_target(sanitize=False, sanitizers=['address'])
        cpp_flags, _r, _s = target._get_cc_flags()
        self.assertIn('-fno-sanitize=address', cpp_flags)

    def test_instrumented_target_has_no_override(self):
        target = self._cc_target(sanitize=True, sanitizers=['address'])
        cpp_flags, _r, _s = target._get_cc_flags()
        self.assertNotIn('-fno-sanitize=address', cpp_flags)

    def test_no_sanitizer_no_override(self):
        target = self._cc_target(sanitize=False, sanitizers=[])
        cpp_flags, _r, _s = target._get_cc_flags()
        self.assertNotIn('-fno-sanitize=address', cpp_flags)


if __name__ == '__main__':
    unittest.main()
