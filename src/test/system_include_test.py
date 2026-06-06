# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>

"""Unit tests for the `-isystem` include-path machinery.

Tests the in-process plumbing only -- `_get_cc_vars`, `_get_cc_flags`,
`_get_incs_list`, `_export_incs_list`. End-to-end BUILD-file integration
of the new `system_include` / `system_export_incs` attributes is
exercised by the existing integration suites.
"""

import unittest

import blade_test  # noqa: F401  -- adds src/blade to sys.path


class _FakeTarget:
    """Minimal duck-typed stand-in for the deps of a CcTarget under test.

    The methods/attributes accessed by ``_export_incs_list`` are just
    ``attr.get('export_incs', ...)`` and ``attr.get('system_export_incs', ...)``,
    so a bare dict is enough.
    """

    def __init__(self, export_incs=None, system_export_incs=None):
        self.attr = {}
        if export_incs is not None:
            self.attr['export_incs'] = list(export_incs)
        if system_export_incs is not None:
            self.attr['system_export_incs'] = list(system_export_incs)


class _CcLike:
    """Just enough of CcTarget to exercise the include-splitting methods."""

    def __init__(self, incs=(), export_incs=(), system_export_incs=(),
                 dep_targets=None):
        # The real CcTarget reads these via attr.get(...) in _get_incs_list.
        self.attr = {
            'incs': list(incs),
            'export_incs': list(export_incs),
            'system_export_incs': list(system_export_incs),
            'defs': [],
            'extra_cppflags': [],
            'warning': 'yes',
        }
        # Fake dep wiring: expanded_deps holds opaque keys; target_database
        # resolves them to fake targets.
        self.target_database = {}
        self.expanded_deps = []
        for i, t in enumerate(dep_targets or []):
            key = 'fake://dep_%d' % i
            self.target_database[key] = t
            self.expanded_deps.append(key)

    # Bind the real methods. CcTarget defines them; we don't want to
    # duplicate logic, just exercise the actual code.
    from blade.cc_targets import CcTarget
    _export_incs_list = CcTarget._export_incs_list
    _get_incs_list = CcTarget._get_incs_list
    _get_cc_flags = CcTarget._get_cc_flags


class ExportIncsListTest(unittest.TestCase):
    """``_export_incs_list`` returns (regular, system) collected from deps."""

    def testSplitsRegularAndSystem(self):
        deps = [
            _FakeTarget(export_incs=['a/include']),
            _FakeTarget(system_export_incs=['b/include']),
            _FakeTarget(export_incs=['c/include'], system_export_incs=['d/include']),
        ]
        cc = _CcLike(dep_targets=deps)
        regular, system = cc._export_incs_list()
        self.assertEqual(regular, ['a/include', 'c/include'])
        self.assertEqual(system, ['b/include', 'd/include'])

    def testSkipsBuiltinSystemDeps(self):
        # deps like '#pthread' are link-only system libraries and must be
        # ignored by the include walker.
        cc = _CcLike()
        cc.target_database = {}
        cc.expanded_deps = ['#pthread']
        regular, system = cc._export_incs_list()
        self.assertEqual(regular, [])
        self.assertEqual(system, [])


class GetIncsListTest(unittest.TestCase):
    """``_get_incs_list`` merges own attrs with dep contributions."""

    def testOwnIncsAndExportIncsAreRegular(self):
        cc = _CcLike(incs=['priv'], export_incs=['pub'])
        regular, system = cc._get_incs_list()
        self.assertEqual(regular, ['priv', 'pub'])
        self.assertEqual(system, [])

    def testOwnSystemExportIncsGoToSystem(self):
        cc = _CcLike(system_export_incs=['sysinc'])
        regular, system = cc._get_incs_list()
        self.assertEqual(regular, [])
        self.assertEqual(system, ['sysinc'])

    def testDedupesWithinEachList(self):
        cc = _CcLike(
            incs=['shared'], export_incs=['shared'],
            dep_targets=[_FakeTarget(export_incs=['shared'])],
        )
        regular, _ = cc._get_incs_list()
        # 'shared' appears 3 times across own incs / own export_incs / dep
        # export_incs; stable_unique collapses to one.
        self.assertEqual(regular, ['shared'])

    def testMixedOwnAndDep(self):
        cc = _CcLike(
            export_incs=['priv'],
            system_export_incs=['priv_sys'],
            dep_targets=[
                _FakeTarget(export_incs=['dep_reg']),
                _FakeTarget(system_export_incs=['dep_sys']),
            ],
        )
        regular, system = cc._get_incs_list()
        self.assertEqual(regular, ['priv', 'dep_reg'])
        self.assertEqual(system, ['priv_sys', 'dep_sys'])


class GetCcFlagsTest(unittest.TestCase):
    """``_get_cc_flags`` returns the (cppflags, regular_incs, system_incs) triple."""

    def testReturnsTriple(self):
        cc = _CcLike(
            export_incs=['reg'],
            system_export_incs=['sys'],
        )
        cppflags, regular, system = cc._get_cc_flags()
        # defs is empty, extra_cppflags is empty -> cppflags is empty
        self.assertEqual(cppflags, [])
        self.assertEqual(regular, ['reg'])
        self.assertEqual(system, ['sys'])


class DeclareHdrsVirtualPathTest(unittest.TestCase):
    """``declare_hdrs`` must register virtual paths for BOTH export_incs AND
    system_export_incs -- a system_include=True target with hdrs under a
    prefix must still resolve the consumer's `#include "foo.h"` back to
    itself, the same way regular `-I` targets do (see blade-build#1227)."""

    def setUp(self):
        # The module-level registry is shared across tests; snapshot+restore.
        from blade import cc_targets
        self._saved_map = dict(cc_targets._hdr_targets_map)

    def tearDown(self):
        from blade import cc_targets
        cc_targets._hdr_targets_map.clear()
        cc_targets._hdr_targets_map.update(self._saved_map)

    def testRegistersVirtualPathFromSystemExportIncs(self):
        from blade import cc_targets

        class _FakeTargetWithHdrs:
            def __init__(self, key, src_dir, export_incs=(), system_export_incs=()):
                self.key = key
                self.build_dir = 'build64_release'
                self._src_dir = src_dir
                self.attr = {}
                if export_incs:
                    self.attr['export_incs'] = list(export_incs)
                if system_export_incs:
                    self.attr['system_export_incs'] = list(system_export_incs)

            def _source_file_path(self, hdr):
                # Mimic Target._source_file_path: prepend the package path.
                return self._src_dir + '/' + hdr if self._src_dir else hdr

        target = _FakeTargetWithHdrs(
            key=('thirdparty/foo', 'foo'),
            src_dir='',
            system_export_incs=['thirdparty/foo/include'],
        )
        cc_targets.declare_hdrs(target, ['thirdparty/foo/include/foo/foo.h'])

        # Full path is always registered.
        self.assertIn('thirdparty/foo/include/foo/foo.h',
                      cc_targets._hdr_targets_map)
        # The include-search-path-relative form ('foo/foo.h') must also be
        # registered against the same target, even though the search-path
        # was declared as system_export_incs (not export_incs).
        self.assertIn('foo/foo.h', cc_targets._hdr_targets_map)
        self.assertIn(target.key,
                      cc_targets._hdr_targets_map['foo/foo.h'])


if __name__ == '__main__':
    unittest.main()
