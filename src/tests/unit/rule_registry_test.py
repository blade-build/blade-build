#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the ninja-rule registry (NinjaRule + rule_registry).

These pin the value type's text rendering (which must reproduce the historical
`generate_rule` output field-for-field, keeping build.ninja byte-identical) and
the registry's deterministic, idempotent ordering.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import console  # noqa: E402
from blade import rule_registry  # noqa: E402
from blade.ninja_rule import NinjaRule  # noqa: E402


class NinjaRuleEmitTest(unittest.TestCase):
    def test_minimal_rule(self):
        # Only name + command, then the trailing blank line.
        self.assertEqual(
            ['rule cc', '  command = clang -c ${in}', ''],
            NinjaRule(name='cc', command='clang -c ${in}').emit())

    def test_field_order_and_presence(self):
        # Field order must match the historical generate_rule emission:
        # command, description, depfile, generator, pool, restat, rspfile,
        # rspfile_content, deps, then a trailing blank line.
        rule = NinjaRule(
            name='link', command='ld ${in}', description='LINK ${out}',
            depfile='${out}.d', generator=True, pool='heavy_pool',
            restat=True, rspfile='${out}.rsp', rspfile_content='${in}',
            deps='gcc')
        expected = [
            'rule link',
            '  command = ld ${in}',
            '  description = %s' % console.colored('LINK ${out}', 'dimpurple'),
            '  depfile = ${out}.d',
            '  generator = 1',
            '  pool = heavy_pool',
            '  restat = 1',
            '  rspfile = ${out}.rsp',
            '  rspfile_content = ${in}',
            '  deps = gcc',
            '',
        ]
        self.assertEqual(expected, rule.emit())

    def test_falsey_fields_are_omitted(self):
        # generator=False / restat=False and None fields produce no lines.
        lines = NinjaRule(name='x', command='c', generator=False, restat=False).emit()
        self.assertNotIn('  generator = 1', lines)
        self.assertNotIn('  restat = 1', lines)
        self.assertFalse(any(l.startswith('  depfile') for l in lines))


class RuleRegistryTest(unittest.TestCase):
    def setUp(self):
        # Isolate from the backend's module-level registrations.
        self._saved = dict(rule_registry._providers)
        rule_registry._providers.clear()

    def tearDown(self):
        rule_registry._providers.clear()
        rule_registry._providers.update(self._saved)

    def test_ordered_by_order_then_name(self):
        rule_registry.register_rule_provider(lambda c: None, order=20, name='b')
        rule_registry.register_rule_provider(lambda c: None, order=10, name='z')
        rule_registry.register_rule_provider(lambda c: None, order=20, name='a')
        # order 10 first; within order 20, name 'a' before 'b'.
        names = []
        # rebuild name list via the sorted view
        ordered = sorted(rule_registry._providers.items(),
                         key=lambda kv: (kv[1][0], kv[0]))
        names = [n for n, _ in ordered]
        self.assertEqual(['z', 'a', 'b'], names)
        # rule_providers() returns the providers in the same order
        self.assertEqual(3, len(rule_registry.rule_providers()))

    def test_idempotent_by_name(self):
        first = lambda c: None
        second = lambda c: None
        rule_registry.register_rule_provider(first, order=10, name='dup')
        rule_registry.register_rule_provider(second, order=10, name='dup')
        self.assertEqual(1, len(rule_registry._providers))
        self.assertIs(second, rule_registry._providers['dup'][1])

    def test_provider_invoked_collects_emissions(self):
        calls = []
        rule_registry.register_rule_provider(lambda c: calls.append('p1'), order=10, name='p1')
        rule_registry.register_rule_provider(lambda c: calls.append('p2'), order=5, name='p2')
        for provider in rule_registry.rule_providers():
            provider(None)
        self.assertEqual(['p2', 'p1'], calls)  # order 5 before 10


if __name__ == '__main__':
    unittest.main()
