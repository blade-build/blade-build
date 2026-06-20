#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors. All rights reserved.

"""Unit tests for the `blade init` subcommand (#504)."""

import os
import sys
import tempfile
import types
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import init_command  # noqa: E402


class ParseLangsTest(unittest.TestCase):
    """Cover init_command.parse_langs."""

    def test_default_is_cc(self):
        self.assertEqual(['cc'], init_command.parse_langs(None))
        self.assertEqual(['cc'], init_command.parse_langs(''))

    def test_aliases_map_to_canonical(self):
        self.assertEqual(['cc'], init_command.parse_langs('c++'))
        self.assertEqual(['python'], init_command.parse_langs('py'))
        self.assertEqual(['go'], init_command.parse_langs('golang'))

    def test_multiple_ordered_and_deduped(self):
        self.assertEqual(['java', 'python'],
                         init_command.parse_langs('java, python'))
        self.assertEqual(['cc'], init_command.parse_langs('cc,c++,cpp'))

    def test_all_expands(self):
        self.assertEqual(['cc', 'java', 'scala', 'go', 'python', 'proto'],
                         init_command.parse_langs('all'))

    def test_unknown_lang_is_fatal(self):
        with self.assertRaises(SystemExit):
            init_command.parse_langs('rust')


class GenerateBladeRootTest(unittest.TestCase):
    """Cover init_command.generate_blade_root."""

    def test_header_and_global_always_present(self):
        text = init_command.generate_blade_root(['cc'])
        self.assertIn('BLADE_ROOT marks the root directory', text)
        self.assertIn('# global_config(', text)
        self.assertTrue(text.endswith('\n'))

    def test_only_requested_language_blocks(self):
        text = init_command.generate_blade_root(['java'])
        self.assertIn('# java_config(', text)
        self.assertNotIn('# cc_config(', text)

    def test_all_languages(self):
        text = init_command.generate_blade_root(
            init_command.parse_langs('all'))
        for needle in ('# cc_config(', '# java_config(', 'scala_config(',
                       'go_config(', 'Python', 'proto_library_config('):
            self.assertIn(needle, text)


class RunInitTest(unittest.TestCase):
    """Cover init_command.run_init: creation and the nested-workspace guard."""

    def setUp(self):
        self.cur = os.getcwd()
        # realpath so macOS /var -> /private/var doesn't confuse path compares.
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix='blade_init_'))
        os.chdir(self.tmp)

    def tearDown(self):
        os.chdir(self.cur)
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _opts(self, lang='cc', force=False):
        return types.SimpleNamespace(lang=lang, force=force)

    def test_creates_in_clean_dir(self):
        self.assertEqual(0, init_command.run_init(self._opts()))
        self.assertTrue(os.path.exists('BLADE_ROOT'))
        with open('BLADE_ROOT') as f:
            self.assertIn('# cc_config(', f.read())

    def _refusal_message(self, opts):
        from unittest import mock
        with mock.patch.object(init_command.console, 'error') as err:
            rc = init_command.run_init(opts)
        self.assertEqual(1, rc)
        return err.call_args[0][0] if err.call_args else ''

    def test_refuses_when_cwd_is_already_a_root(self):
        with open('BLADE_ROOT', 'w') as f:
            f.write('cc_config()\n')
        msg = self._refusal_message(self._opts())
        self.assertIn('already a workspace root', msg)
        with open('BLADE_ROOT') as f:
            self.assertEqual('cc_config()\n', f.read())  # untouched

    def test_refuses_in_subdir_of_existing_workspace(self):
        # tmp/ is a workspace; initializing in tmp/sub would nest.
        open('BLADE_ROOT', 'w').close()
        os.makedirs('sub')
        os.chdir('sub')
        msg = self._refusal_message(self._opts())
        self.assertIn('nested workspace', msg)
        self.assertFalse(os.path.exists('BLADE_ROOT'))

    def test_force_overwrites_root(self):
        with open('BLADE_ROOT', 'w') as f:
            f.write('old\n')
        self.assertEqual(0, init_command.run_init(self._opts(force=True)))
        with open('BLADE_ROOT') as f:
            self.assertIn('BLADE_ROOT marks the root directory', f.read())

    def test_force_allows_nested_workspace(self):
        open('BLADE_ROOT', 'w').close()
        os.makedirs('sub')
        os.chdir('sub')
        self.assertEqual(0, init_command.run_init(self._opts(force=True)))
        self.assertTrue(os.path.exists('BLADE_ROOT'))


if __name__ == '__main__':
    unittest.main()
