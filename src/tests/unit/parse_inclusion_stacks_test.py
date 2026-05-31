#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for blade.inclusion_check._parse_inclusion_stacks.

The `.incstk` file omits absolute/system headers (the GCC awk splitter keeps
only paths not starting with `/`; the MSVC wrapper keeps only in-workspace
paths) but preserves the compiler's original nesting depth. So a kept header
nested under a filtered system header shows up with a **depth gap**. The parser
must tolerate that gap (treat the subtree as untracked) instead of aborting the
build with an AssertionError -- the bug in #953.
"""

import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import inclusion_check  # noqa: E402  (sys.path tweak above)

_BUILD_DIR = 'build64_release'


def _parse(content):
    with tempfile.NamedTemporaryFile('w', suffix='.incstk', delete=False) as f:
        f.write(content)
        path = f.name
    try:
        return inclusion_check._parse_inclusion_stacks(path, _BUILD_DIR)
    finally:
        os.unlink(path)


class ParseInclusionStacksTest(unittest.TestCase):
    def test_contiguous_stack_is_parsed(self):
        # Happy path (the function's docstring example): no gaps.
        direct, stacks = _parse(
            '. ./app/example/foo.h\n'
            '.. build64_release/app/example/proto/foo.pb.h\n'
            '... build64_release/common/rpc/rpc_service.pb.h\n'
            '. build64_release/app/example/proto/bar.pb.h\n'
            '. ./common/rpc/rpc_client.h\n'
            '.. build64_release/common/rpc/rpc_options.pb.h\n')
        self.assertEqual(
            ['app/example/foo.h', 'app/example/proto/bar.pb.h', 'common/rpc/rpc_client.h'],
            direct)
        self.assertEqual(
            [['app/example/foo.h', 'app/example/proto/foo.pb.h'],
             ['app/example/proto/bar.pb.h'],
             ['common/rpc/rpc_client.h', 'common/rpc/rpc_options.pb.h']],
            stacks)

    def test_depth_gap_does_not_crash(self):
        # #953: a.h (level 1) -> [system header at level 2, filtered out] ->
        # b.h (level 3). The jump 1->3 must not raise; b.h is reached only via
        # the system header, so it is not tracked.
        direct, stacks = _parse('. foo/a.h\n... foo/b.h\n')
        self.assertEqual(['foo/a.h'], direct)
        self.assertEqual([], stacks)

    def test_gap_on_first_line_does_not_crash(self):
        # The first kept header is already nested under a filtered system one.
        direct, stacks = _parse('.. foo/a.h\n')
        self.assertEqual([], direct)
        self.assertEqual([], stacks)

    def test_parsing_resumes_after_a_gap(self):
        # After skipping the gap subtree, a later level-1 include is tracked.
        direct, stacks = _parse('. foo/a.h\n... foo/deep.h\n. foo/c.h\n')
        self.assertEqual(['foo/a.h', 'foo/c.h'], direct)
        self.assertEqual([], stacks)


if __name__ == '__main__':
    unittest.main()
