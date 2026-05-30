#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.

"""Unit tests for the unused cc dependency check (issue #1155).

Exercises ``inclusion_check.Checker._check_unused_deps`` in isolation: a dep is
flagged only when none of its public headers is directly included, and is
exempt when it is header-less (``hdrs = []``), listed in ``keep_deps``, or
suppressed via config; the target itself is never flagged.
"""

import os
import pickle
import shutil
import sys
import tempfile
import unittest
from typing import Sequence

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import inclusion_check  # noqa: E402


class UnusedDepsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = 'pkg'
        self.key = 'pkg:t'

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _checker(self, deps: Sequence[str], header_less: Sequence[str] = (),
                 keep_deps: Sequence[str] = (), suppress: Sequence[str] = ()) -> inclusion_check.Checker:
        """Build a Checker over a fabricated global declaration.

        Each non-header-less dep ``pkg:x`` owns the public header ``pkg/x.h``.
        """
        header_less_keys = set(header_less)
        public_hdrs = {}
        for dep in deps:
            if dep in header_less_keys:
                continue
            name = dep.split(':')[-1]
            public_hdrs.setdefault('%s/%s.h' % (self.path, name), set()).add(dep)
        declaration = {
            'public_hdrs': public_hdrs,
            'public_incs': {},
            'private_hdrs': {},
            'header_less': header_less_keys,
            'allowed_undeclared_hdrs': set(),
        }
        with open(os.path.join(self.tmp, 'inclusion_declaration.data'), 'wb') as f:
            pickle.dump(declaration, f)
        target = {
            'type': 'cc_library', 'name': 't', 'path': self.path, 'key': self.key,
            'deps': list(deps), 'build_dir': self.tmp, 'source_location': 'pkg/BUILD:1',
            'expanded_srcs': [], 'expanded_hdrs': [],
            'declared_hdrs': set(), 'declared_incs': set(),
            'declared_genhdrs': set(), 'declared_genincs': set(),
            'hdrs_deps': {}, 'private_hdrs_deps': {}, 'allowed_undeclared_hdrs': {},
            'suppress': {}, 'severity': 'error',
            'unused_deps_severity': 'warning',
            'unused_deps_suppress': list(suppress),
            'keep_deps': list(keep_deps),
        }
        return inclusion_check.Checker(target)

    def _hdr(self, dep: str) -> str:
        return '%s/%s.h' % (self.path, dep.split(':')[-1])

    def test_used_dep_not_flagged(self):
        c = self._checker(['pkg:a'])
        self.assertEqual(c._check_unused_deps({self._hdr('pkg:a')}), set())

    def test_unused_dep_flagged(self):
        c = self._checker(['pkg:a', 'pkg:b'])
        # Only a's header is included -> b is unused.
        self.assertEqual(c._check_unused_deps({self._hdr('pkg:a')}), {'pkg:b'})

    def test_header_less_dep_exempt(self):
        c = self._checker(['pkg:a', 'pkg:hl'], header_less=['pkg:hl'])
        # hl has no public headers (hdrs = []) -> exempt even though unused.
        self.assertEqual(c._check_unused_deps({self._hdr('pkg:a')}), set())

    def test_keep_deps_exempt(self):
        c = self._checker(['pkg:a', 'pkg:b'], keep_deps=['pkg:b'])
        self.assertEqual(c._check_unused_deps({self._hdr('pkg:a')}), set())

    def test_suppress_exempt(self):
        c = self._checker(['pkg:a', 'pkg:b'], suppress=['pkg:b'])
        self.assertEqual(c._check_unused_deps({self._hdr('pkg:a')}), set())

    def test_self_never_flagged(self):
        # The target may own its own headers; depending on self is never "unused".
        c = self._checker([self.key, 'pkg:b'])
        self.assertEqual(c._check_unused_deps(set()), {'pkg:b'})

    def test_multiple_unused(self):
        c = self._checker(['pkg:a', 'pkg:b', 'pkg:c'])
        self.assertEqual(c._check_unused_deps({self._hdr('pkg:a')}), {'pkg:b', 'pkg:c'})

    def test_system_lib_dep_exempt(self):
        # `#:dl` / `#:pthread` etc. have headers (`<dlfcn.h>`, `<pthread.h>`)
        # but blade has no system-header -> system-lib mapping to consult, so
        # the header-based unused-deps check has nothing to evaluate them
        # against -- exempt them. See issue #1171 follow-up.
        c = self._checker(['pkg:a', '#:dl', '#:pthread'])
        self.assertEqual(
            c._check_unused_deps({self._hdr('pkg:a')}), set())

    def test_system_lib_does_not_mask_regular_unused(self):
        # Having a system lib in deps should not change how regular unused
        # cc_library deps are flagged.
        c = self._checker(['pkg:a', 'pkg:b', '#:dl'])
        self.assertEqual(
            c._check_unused_deps({self._hdr('pkg:a')}), {'pkg:b'})


if __name__ == '__main__':
    unittest.main()
