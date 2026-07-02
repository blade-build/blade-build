#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Guard: every integration test class is registered in blade_main_test.py.

CI runs the integration tests only through src/test/blade_main_test.py, whose
suite is built from an explicit `TEST_CASES` list. Historically new
src/test/*_test.py files were silently dropped from that list and so never ran
in CI (e.g. go_build_test). This test parses (via AST, no imports) every
src/test/*_test.py, finds classes that define a `test*` method, and fails if any
is absent from `TEST_CASES` -- making that omission impossible to reintroduce.
"""

import ast
import glob
import os
import unittest

_TEST_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'test'))  # -> src/test
_RUNNER = os.path.join(_TEST_DIR, 'blade_main_test.py')


def _defines_own_test_method(classdef):
    return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name.startswith('test')
               for n in classdef.body)


def _runnable_test_classes():
    """{class_name: filename} for classes that define their own `test*` method.

    A class with a `test*` method is something unittest will run, so it must be
    registered. Pure base/helper classes (setUp/helpers only, e.g.
    GoBuildTestBase) define no `test*` method and are correctly ignored.
    """
    found = {}
    for path in sorted(glob.glob(os.path.join(_TEST_DIR, '*_test.py'))):
        base = os.path.basename(path)
        if base == 'blade_main_test.py':      # the runner itself
            continue
        with open(path, encoding='utf-8') as f:
            tree = ast.parse(f.read())
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and _defines_own_test_method(node):
                found[node.name] = base
    return found


def _registered_class_names():
    """Names listed in blade_main_test.py's `TEST_CASES`."""
    with open(_RUNNER, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == 'TEST_CASES'
                for t in node.targets):
            return {e.id for e in node.value.elts if isinstance(e, ast.Name)}
    return set()


class IntegrationSuiteCoverageTest(unittest.TestCase):
    def test_every_integration_test_is_registered(self):
        registered = _registered_class_names()
        self.assertTrue(registered,
                        'Could not find TEST_CASES in %s' % _RUNNER)
        runnable = _runnable_test_classes()
        missing = {c: f for c, f in runnable.items() if c not in registered}
        self.assertEqual(
            {}, missing,
            'Integration test classes missing from blade_main_test.py '
            'TEST_CASES (they would never run in CI):\n' +
            '\n'.join('  %s  (%s)' % (c, f) for c, f in sorted(missing.items())))


if __name__ == '__main__':
    unittest.main()
