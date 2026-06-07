#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Tests for user-defined custom rules (issue #829): the attr schema, attribute
coercion/validation, fingerprint coverage, edge emission, and the `.bld`-only
exposure of `define_rule` / `attr`.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import build_rules  # noqa: E402
from blade import custom_rule_target as crt  # noqa: E402
from blade import gen_command as gc  # noqa: E402
from blade.custom_rule_target import CustomRuleTarget, attr, define_rule  # noqa: E402


class AttrSchemaTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(attr.string(default='x').kind, 'string')
        self.assertEqual(attr.bool(default=True).default, True)
        self.assertEqual(attr.int(default=3).kind, 'int')
        self.assertEqual(attr.string_list().kind, 'string_list')
        self.assertEqual(attr.src_list(exts=['y']).exts, ['y'])
        self.assertEqual(attr.dep_list().kind, 'dep_list')
        self.assertEqual(attr.out_list().kind, 'out_list')

    def test_default_of_lists_are_fresh(self):
        spec = attr.string_list(default=['a'])
        d1 = crt._default_of(spec)
        d1.append('b')
        self.assertEqual(crt._default_of(spec), ['a'])  # not mutated

    def test_coerce(self):
        bad = []
        self.assertEqual(crt._coerce(attr.string_list(), 'a', bad, 'x'), ['a'])
        self.assertEqual(crt._coerce(attr.string(), 'a', bad, 'x'), 'a')
        self.assertEqual(crt._coerce(attr.bool(), True, bad, 'x'), True)
        self.assertEqual(crt._coerce(attr.int(), 5, bad, 'x'), 5)
        self.assertEqual(bad, [])
        # type mismatches are recorded
        crt._coerce(attr.int(), 'nope', bad, 'n')
        crt._coerce(attr.bool(), 'nope', bad, 'b')
        self.assertEqual([n for n, _ in bad], ['n', 'b'])


class DefineRuleTest(unittest.TestCase):
    def test_returns_named_callable(self):
        fn = define_rule('awesome_library', attrs={'srcs': attr.src_list()},
                         action=lambda ctx: None)
        self.assertTrue(callable(fn))
        self.assertEqual(fn.__name__, 'awesome_library')

    def test_extension_only_exposure(self):
        # define_rule / attr are visible to .bld extensions, never to BUILD files
        self.assertNotIn('define_rule', build_rules.get_all())
        self.assertNotIn('attr', build_rules.get_all())
        ext = build_rules.get_all_for_extension()
        self.assertIn('define_rule', ext)
        self.assertIn('attr', ext)


def _action_a(ctx):
    ctx.declare_output('a.out')


def _action_b(ctx):
    ctx.declare_output('b.out')          # different body -> different source


def _bare_target():
    """A CustomRuleTarget bypassing Target.__init__ (which needs the build
    manager); we set only what the method under test reads."""
    t = CustomRuleTarget.__new__(CustomRuleTarget)
    t.error = mock.Mock()
    return t


class FingerprintTest(unittest.TestCase):
    def _target(self, action):
        t = _bare_target()
        t._action = action
        t._schema = {'srcs': attr.src_list(exts=['x'])}
        t.attr = {'rule_type': 'r', 'custom_attrs': {'opt': '-O2'}, 'description': 'CUSTOM'}
        return t

    def test_action_fingerprint_changes_with_source(self):
        fa = self._target(_action_a)._action_fingerprint()
        fb = self._target(_action_b)._action_fingerprint()
        self.assertNotEqual(fa, fb)
        # stable for the same action
        self.assertEqual(fa, self._target(_action_a)._action_fingerprint())

    def test_entropy_is_serializable(self):
        # the action object must NEVER leak into entropy (Target.fingerprint
        # asserts no ' object at 0x' in the stringified entropy)
        entropy = self._target(_action_a)._fingerprint_entropy()
        self.assertNotIn(' object at 0x', str(sorted(entropy.items())))
        self.assertIn('custom_rule_action', entropy)
        self.assertIn('custom_rule_schema', entropy)


class EmitShellEdgeTest(unittest.TestCase):
    def _target(self):
        t = _bare_target()
        t.name = 'demo'
        t.srcs = ['a.txt']
        t.path = 'demo'
        t.build_dir = 'bd'
        t.fullname = '//demo:demo'
        t._outputs = ['bd/demo/out.txt']
        t._edge_seq = 0
        t.deps = []
        t.attr = {'custom_attrs': {}, 'description': 'CUSTOM'}
        t.blade = mock.Mock()
        t.blade.get_root_dir.return_value = ''
        t._expand_srcs = lambda: ['demo/a.txt']
        t._implicit_dependencies = lambda: []
        t._source_file_path = lambda p: p
        t._rules = []
        t._write_rule = lambda text: t._rules.append(text)
        t.generate_build = mock.Mock()
        return t

    def test_run_shell_emits_rule_and_edge(self):
        t = self._target()
        with mock.patch.object(gc.os, 'name', 'posix'):  # deterministic raw-sh wrap
            t._emit_shell_edge('echo hi > $OUTS', None, None, None, None, None, None, None)
        rule_text = '\n'.join(t._rules)
        self.assertIn('__rule__', rule_text)
        self.assertIn('echo hi > ${out}', rule_text)     # $OUTS -> ${out}
        self.assertIn('test -e', rule_text)              # portable output check
        kw = t.generate_build.call_args
        self.assertEqual(kw.args[1], ['bd/demo/out.txt'])  # outputs
        self.assertEqual(kw.kwargs['inputs'], ['demo/a.txt'])

    def test_run_shell_requires_a_command(self):
        t = self._target()
        t._emit_shell_edge(None, None, None, None, None, None, None, None)
        t.error.assert_called()
        t.generate_build.assert_not_called()


if __name__ == '__main__':
    unittest.main()
