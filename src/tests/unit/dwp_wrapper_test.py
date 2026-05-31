#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for blade.dwp_wrapper.

The dwp wrapper collects ``.dwo`` files (split DWARF, DebugFission) for a
binary and invokes the ``dwp`` tool. The tool invocation and ``ar t`` archive
listing need real toolchain binaries, but the input plumbing -- response-file
expansion, ``.o`` -> ``.dwo`` mapping, de-duplicated collection, and the
empty-input short circuit -- is pure and is what these tests pin.
"""

import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import dwp_wrapper  # noqa: E402  (sys.path tweak above)


class ExpandResponseFilesTest(unittest.TestCase):
    def test_plain_args_pass_through(self):
        self.assertEqual(['a.o', 'b.o'],
                         dwp_wrapper.expand_response_files(['a.o', 'b.o']))

    def test_at_file_is_expanded_skipping_comments_and_blanks(self):
        with tempfile.TemporaryDirectory() as d:
            rsp = os.path.join(d, 'inputs.rsp')
            with open(rsp, 'w') as f:
                f.write('# a comment\n\nx.o y.o\nz.o\n')
            self.assertEqual(
                ['head.o', 'x.o', 'y.o', 'z.o', 'tail.o'],
                dwp_wrapper.expand_response_files(['head.o', '@' + rsp, 'tail.o']))


class FindDwoForObjectTest(unittest.TestCase):
    def test_returns_path_when_dwo_exists(self):
        with tempfile.TemporaryDirectory() as d:
            obj = os.path.join(d, 'foo.o')
            dwo = os.path.join(d, 'foo.dwo')
            open(dwo, 'w').close()
            self.assertEqual(dwo, dwp_wrapper.find_dwo_for_object(obj))

    def test_returns_none_when_dwo_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(
                dwp_wrapper.find_dwo_for_object(os.path.join(d, 'foo.o')))


class CollectDwoFilesTest(unittest.TestCase):
    def test_object_with_and_without_dwo(self):
        with tempfile.TemporaryDirectory() as d:
            have, lack = os.path.join(d, 'a.o'), os.path.join(d, 'b.o')
            open(have, 'w').close()
            open(lack, 'w').close()
            open(os.path.join(d, 'a.dwo'), 'w').close()  # only a has a .dwo
            self.assertEqual([os.path.join(d, 'a.dwo')],
                             dwp_wrapper.collect_dwo_files([have, lack]))

    def test_direct_dwo_and_dedup(self):
        with tempfile.TemporaryDirectory() as d:
            dwo = os.path.join(d, 'a.dwo')
            obj = os.path.join(d, 'a.o')
            open(dwo, 'w').close()
            open(obj, 'w').close()
            # The .o maps to a.dwo and the .dwo is passed directly -> one entry.
            self.assertEqual([dwo], dwp_wrapper.collect_dwo_files([obj, dwo]))

    def test_nonexistent_input_skipped(self):
        self.assertEqual([], dwp_wrapper.collect_dwo_files(['/no/such/file.o']))


class RunDwpTest(unittest.TestCase):
    def test_empty_dwo_list_writes_empty_output(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, 'bin.dwp')
            self.assertEqual(0, dwp_wrapper.run_dwp(out, []))
            self.assertTrue(os.path.exists(out))
            self.assertEqual(0, os.path.getsize(out))


if __name__ == '__main__':
    unittest.main()
