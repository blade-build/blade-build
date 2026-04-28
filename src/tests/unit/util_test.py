#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.util normalization helpers.

"""Tests for :func:`blade.util.var_to_list` and
:func:`blade.util.var_to_list_or_none`.

These two helpers are the load-bearing boundary between the BUILD-file
surface (which accepts ``srcs='foo.cc'`` or ``srcs=['a.cc', 'b.cc']``) and
the rest of the Python code (which assumes a plain ``list[str]``). Breaking
their contract would cascade into every rule-entry function, so we pin the
behaviour down with direct unit tests.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade.util import var_to_list, var_to_list_or_none  # noqa: E402


class VarToListTest(unittest.TestCase):
    """Cover every branch of ``var_to_list``."""

    def test_none_returns_empty_list(self):
        self.assertEqual(var_to_list(None), [])

    def test_list_input_returns_shallow_copy(self):
        original = ['a', 'b', 'c']
        result = var_to_list(original)
        self.assertEqual(result, ['a', 'b', 'c'])
        # Mutating the result must not touch the caller's list. This is the
        # whole point of taking a copy on the way in.
        result.append('d')
        self.assertEqual(original, ['a', 'b', 'c'])

    def test_empty_list_returns_empty_list(self):
        self.assertEqual(var_to_list([]), [])

    def test_scalar_string_wrapped(self):
        self.assertEqual(var_to_list('foo.cc'), ['foo.cc'])

    def test_tuple_materialized(self):
        self.assertEqual(var_to_list(('a', 'b')), ['a', 'b'])

    def test_set_materialized(self):
        # Order is not guaranteed for sets, so compare as sets.
        self.assertEqual(set(var_to_list({'a', 'b'})), {'a', 'b'})

    def test_frozenset_materialized(self):
        # frozenset matters in practice: _SOURCE_FILE_EXTS reaches
        # Target.__init__ via src_exts as a set and must not be wrapped
        # as a single-element list.
        self.assertEqual(set(var_to_list(frozenset({'a', 'b'}))), {'a', 'b'})

    def test_always_returns_fresh_object(self):
        # Same input passed in twice must never alias the same output.
        original = ['a']
        first = var_to_list(original)
        second = var_to_list(original)
        self.assertIsNot(first, second)


class VarToListOrNoneTest(unittest.TestCase):
    """Cover the None-sentinel variant."""

    def test_none_stays_none(self):
        # Crucial: ``None`` must not collapse into ``[]``. Callers use the
        # None vs. [] distinction (e.g. default-visibility vs. visible-to-
        # nobody).
        self.assertIsNone(var_to_list_or_none(None))

    def test_scalar_wrapped(self):
        self.assertEqual(var_to_list_or_none('x'), ['x'])

    def test_list_copied(self):
        original = ['a']
        result = var_to_list_or_none(original)
        self.assertEqual(result, ['a'])
        self.assertIsNotNone(result)
        assert result is not None  # narrow for the type checker
        result.append('b')
        self.assertEqual(original, ['a'])

    def test_empty_list_returns_empty_list_not_none(self):
        # [] is a meaningful input: it means "explicitly empty", which is
        # different from "not configured" (None).
        result = var_to_list_or_none([])
        self.assertEqual(result, [])
        self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
