#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Regression tests for MSVC per-target compile-flag threading.

The MSVC cc/cxx/cxxhdrs rules must consume the per-target ``${includes}`` and
``${cppflags}`` ninja variables that ``CcTarget._get_cc_vars`` produces. They
historically baked only the system include paths into the rule and dropped the
per-target ones, so any target with ``incs`` / ``defs`` silently failed to
compile on MSVC (the blade-test cc suites don't use ``incs``, so the gap went
unnoticed). These tests pin the rule text so that can't regress.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_rule_support  # noqa: E402


class MsvcCompileFlagsTest(unittest.TestCase):
    def _make_gen(self):
        gen = cc_rule_support.CcRuleGenerator.__new__(cc_rule_support.CcRuleGenerator)
        gen.build_toolchain = mock.Mock()
        # Native cl.exe path (a plain Mock's is_clang_cl() would be truthy).
        gen.build_toolchain.is_clang_cl.return_value = False
        gen.build_toolchain.filter_cc_flags = lambda flags, *a: list(flags)
        gen.build_toolchain.get_system_include_paths.return_value = []
        gen.build_accelerator = mock.Mock()
        gen.options = mock.Mock()
        gen.options.profile = 'release'
        gen.options.sanitizers = []
        gen.build_dir = 'build64_release'
        gen._msvc_tee_wrapper_py = mock.Mock(return_value='cc_wrapper.py')
        gen.generate_rule = mock.Mock()
        return gen

    def _rules(self, sanitizers=None):
        gen = self._make_gen()
        if sanitizers is not None:
            gen.options.sanitizers = sanitizers
        section = {
            'msvc_config': {'cppflags': [], 'cflags': [], 'cxxflags': [],
                            'optimize': {'release': ['/O2']},
                            'debug_info_levels': {'mid': []}},
            'cc_config': {'cflags': [], 'cxxflags': [], 'cppflags': [],
                          'extra_incs': []},
            'global_config': {'debug_info_level': 'mid'},
        }
        with mock.patch('blade.cc_rule_support.config') as cfg:
            cfg.get_section.side_effect = lambda n: section[n]
            gen._generate_windows_cc_compile_rules('cl.exe', 'cl.exe')
        return {c.kwargs['name']: c.kwargs['command']
                for c in gen.generate_rule.call_args_list}

    def test_rules_thread_per_target_includes(self):
        """cc / cxx / cxxhdrs must pass per-target ${includes} (the incs)."""
        rules = self._rules()
        for name in ('cc', 'cxx', 'cxxhdrs'):
            self.assertIn('${includes}', rules[name],
                          '%s rule drops per-target includes' % name)

    def test_rules_thread_per_target_cppflags(self):
        """cc / cxx / cxxhdrs must pass per-target ${cppflags} (the defs)."""
        rules = self._rules()
        for name in ('cc', 'cxx', 'cxxhdrs'):
            self.assertIn('${cppflags}', rules[name],
                          '%s rule drops per-target cppflags' % name)

    def test_external_w0_present(self):
        """/external:W0 must be present so /external:I (the -isystem analog)
        actually suppresses 3rd-party header warnings."""
        rules = self._rules()
        for name in ('cc', 'cxx', 'cxxhdrs'):
            self.assertIn('/external:W0', rules[name])

    def test_compiles_reference_sanitize_var(self):
        """cc / cxx carry the overridable ${sanitize} var (the instrumentation
        flags live in that binding, blanked per-target for sanitize=False).
        cxxhdrs only preprocesses, so it doesn't need it. (issue #1038, Phase 3)"""
        rules = self._rules()
        for name in ('cc', 'cxx'):
            self.assertIn('${sanitize}', rules[name])


if __name__ == '__main__':
    unittest.main()
