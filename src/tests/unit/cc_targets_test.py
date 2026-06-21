#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for blade.cc_targets._generate_link_all_symbols_link_flags.

"""Unit tests for CcTarget._generate_link_all_symbols_link_flags.

The method emits linker flags that force every symbol of a static archive
to be pulled in — the idiom protoc-generated code relies on for descriptor
registration (proto_library sets ``link_all_symbols=True`` unconditionally),
and which thrift_library / lex_yacc_target reach for
the same way.

The flag spelling is platform-sensitive:

* GNU ld / gold / lld / mold, plus every BSD with a GNU-ld-compatible
  linker, speak ``-Wl,--whole-archive ... -Wl,--no-whole-archive``.
* Apple's ld64 / ld-prime — the only linker available to any macOS
  toolchain (Apple Clang, Homebrew GCC, Homebrew LLVM) because Mach-O
  has no GNU-ld port — rejects that spelling outright and needs
  ``-Wl,-force_load,<archive>`` once per archive instead.

These tests pin the branch selection so that a regression back to a
hard-coded GNU spelling immediately fails on Darwin CI (and vice versa).
"""

import os
import sys
import unittest  # lgtm[py/import-and-import-from]
from unittest import mock

# Make ``import blade.*`` resolve against the in-tree sources without
# requiring blade to be installed.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402  (sys.path tweak above)


def _bare_cc_target():
    """Build a ``CcTarget`` instance bypassing __init__.

    The flag-generation logic under test reads nothing from ``self``,
    so we avoid the cost and dependencies of a full target construction.
    """
    return cc_targets.CcTarget.__new__(cc_targets.CcTarget)


class GenerateLinkAllSymbolsLinkFlagsTest(unittest.TestCase):
    """Cover every branch of the emitter."""

    def test_empty_input_returns_empty_regardless_of_platform(self):
        target = _bare_cc_target()
        # Emitter must short-circuit before consulting the platform so
        # that callers with no whole-archive libs don't accidentally
        # inject stray flags.
        with mock.patch.object(cc_targets.sys, 'platform', 'linux'):
            self.assertEqual([], target._generate_link_all_symbols_link_flags([]))
        with mock.patch.object(cc_targets.sys, 'platform', 'darwin'):
            self.assertEqual([], target._generate_link_all_symbols_link_flags([]))

    def test_linux_emits_gnu_whole_archive_pair(self):
        target = _bare_cc_target()
        libs = [
            'build64_release/suites/proto_basic/libcontact_proto.a',
            'build64_release/suites/thrift_basic/libping.a',
        ]
        with mock.patch.object(cc_targets.sys, 'platform', 'linux'):
            flags = target._generate_link_all_symbols_link_flags(libs)
        self.assertEqual(
            ['-Wl,--whole-archive'] + libs + ['-Wl,--no-whole-archive'],
            flags,
        )

    def test_darwin_emits_one_force_load_per_archive(self):
        target = _bare_cc_target()
        libs = [
            'build64_release/suites/proto_basic/libcontact_proto.a',
            'build64_release/suites/thrift_basic/libping.a',
        ]
        with mock.patch.object(cc_targets.sys, 'platform', 'darwin'):
            flags = target._generate_link_all_symbols_link_flags(libs)
        # One flag per archive, preserving order — link ordering matters
        # for symbol resolution and we must not silently collapse it.
        self.assertEqual(
            [
                '-Wl,-force_load,build64_release/suites/proto_basic/libcontact_proto.a',
                '-Wl,-force_load,build64_release/suites/thrift_basic/libping.a',
            ],
            flags,
        )

    def test_darwin_does_not_emit_gnu_whole_archive(self):
        # Regression pin: ld64 errors out with ``ld: unknown option:
        # --whole-archive`` if the GNU spelling leaks into the Darwin
        # branch. This test guards that boundary explicitly.
        target = _bare_cc_target()
        with mock.patch.object(cc_targets.sys, 'platform', 'darwin'):
            flags = target._generate_link_all_symbols_link_flags(['a.a'])
        joined = ' '.join(flags)
        self.assertNotIn('--whole-archive', joined)
        self.assertNotIn('--no-whole-archive', joined)

    def test_linux_single_lib_is_wrapped_once(self):
        target = _bare_cc_target()
        with mock.patch.object(cc_targets.sys, 'platform', 'linux'):
            flags = target._generate_link_all_symbols_link_flags(['x.a'])
        self.assertEqual(
            ['-Wl,--whole-archive', 'x.a', '-Wl,--no-whole-archive'],
            flags,
        )

    def test_unknown_platform_falls_back_to_gnu_spelling(self):
        # Anything other than Darwin keeps the GNU spelling — this is
        # the safe default for the long tail of Linux-like platforms
        # (``linux``, ``linux2``, ``freebsd14``, ``openbsd7``, ...).
        target = _bare_cc_target()
        for platform_value in ('linux', 'linux2', 'freebsd14', 'openbsd7'):
            with mock.patch.object(cc_targets.sys, 'platform', platform_value):
                flags = target._generate_link_all_symbols_link_flags(['y.a'])
            self.assertEqual(
                ['-Wl,--whole-archive', 'y.a', '-Wl,--no-whole-archive'],
                flags,
                msg='regressed on sys.platform=%r' % platform_value,
            )


class ResolveLinkerInputFileTest(unittest.TestCase):
    """Cover the singular/deprecated-plural resolver used by export_map and
    linker_script (and their plural aliases version_scripts / linker_scripts).
    """

    def _target(self):
        target = _bare_cc_target()
        target.warnings = []
        target.warning = target.warnings.append
        # _fullpath_sources is exercised elsewhere; here we only care about the
        # selection/warning logic, so make it an identity over the file list.
        target._fullpath_sources = lambda files: list(files)
        return target

    def test_singular_only_no_warning(self):
        target = self._target()
        self.assertEqual(['a.map'],
                         target._resolve_linker_input_file('a.map', None, 'export_map', 'version_scripts'))
        self.assertEqual([], target.warnings)

    def test_none_returns_empty(self):
        target = self._target()
        self.assertEqual([],
                         target._resolve_linker_input_file(None, None, 'export_map', 'version_scripts'))
        self.assertEqual([], target.warnings)

    def test_plural_alias_warns_and_is_used(self):
        target = self._target()
        result = target._resolve_linker_input_file(None, ['old.map'], 'export_map', 'version_scripts')
        self.assertEqual(['old.map'], result)
        self.assertEqual(1, len(target.warnings))
        self.assertIn('version_scripts', target.warnings[0])
        self.assertIn('export_map', target.warnings[0])

    def test_both_given_prefers_singular(self):
        target = self._target()
        result = target._resolve_linker_input_file('new.map', ['old.map'], 'export_map', 'version_scripts')
        self.assertEqual(['new.map'], result)
        # Deprecation warning + a notice that the plural is ignored.
        self.assertEqual(2, len(target.warnings))
        self.assertTrue(any('ignored' in w for w in target.warnings))

    def test_more_than_one_file_keeps_first(self):
        target = self._target()
        result = target._resolve_linker_input_file(['a.map', 'b.map'], None, 'export_map', 'version_scripts')
        self.assertEqual(['a.map'], result)
        self.assertTrue(any('single file' in w for w in target.warnings))


class ExtraCompileFlagsForTest(unittest.TestCase):
    """Per-source-language selection of extra_cflags/cxxflags/asflags (#492)."""

    def _target(self):
        t = cc_targets.CcTarget.__new__(cc_targets.CcTarget)
        t.attr = {
            'extra_cflags': ['-c-only'],
            'extra_cxxflags': ['-cxx-only'],
            'extra_asflags': ['-as-only'],
        }
        return t

    def test_cxx_sources_get_cxxflags(self):
        t = self._target()
        for src in ('a.cc', 'a.cpp', 'a.cxx'):
            self.assertEqual(['-cxx-only'], t._extra_compile_flags_for(src), src)

    def test_asm_sources_get_asflags(self):
        t = self._target()
        for src in ('a.s', 'a.S', 'a.asm'):
            self.assertEqual(['-as-only'], t._extra_compile_flags_for(src), src)

    def test_objc_sources(self):
        # Objective-C++ (.mm) is C++; Objective-C (.m) is C.
        t = self._target()
        self.assertEqual(['-cxx-only'], t._extra_compile_flags_for('a.mm'))
        self.assertEqual(['-c-only'], t._extra_compile_flags_for('a.m'))

    def test_c_and_other_sources_get_cflags(self):
        t = self._target()
        self.assertEqual(['-c-only'], t._extra_compile_flags_for('a.c'))

    def test_unset_returns_empty(self):
        t = cc_targets.CcTarget.__new__(cc_targets.CcTarget)
        t.attr = {}
        self.assertEqual([], t._extra_compile_flags_for('a.cc'))
        self.assertEqual([], t._extra_compile_flags_for('a.c'))


class RuleFromSuffixTest(unittest.TestCase):
    """Source-suffix -> compile rule (cxx for C++/Objective-C++, else cc)."""

    def _target(self):
        return cc_targets.CcTarget.__new__(cc_targets.CcTarget)

    def test_cxx_and_objcxx_use_cxx_rule(self):
        t = self._target()
        for src in ('a.cc', 'a.cpp', 'a.cxx', 'a.mm'):
            self.assertEqual('cxx', t._get_rule_from_suffix(src, secret=False), src)

    def test_c_and_objc_use_cc_rule(self):
        t = self._target()
        for src in ('a.c', 'a.m'):
            self.assertEqual('cc', t._get_rule_from_suffix(src, secret=False), src)

    def test_objc_recognized_as_source(self):
        self.assertIn('m', cc_targets._SOURCE_FILE_EXTS)
        self.assertIn('mm', cc_targets._SOURCE_FILE_EXTS)


class CcLinkPlatformGuardTest(unittest.TestCase):
    """``_cc_link`` must drop GNU-ld-only flags on Darwin instead of letting
    them reach ld64 (which fails with a cryptic ``ld: unknown options``).

    The two flags affected are ``--version-script`` (from ``export_map``) and
    ``-T`` (from ``linker_script``). MSVC has its own path in
    ``_dynamic_cc_library_windows`` and never reaches ``_cc_link``, so it's
    excluded here.
    """

    def _target_with_toolchain(self, target_os):
        target = _bare_cc_target()
        # Minimal attrs so ``_cc_link`` doesn't crash. ``linkflags=None``
        # exercises the "no linkflags" branch; ``extra_linkflags=[]`` lets the
        # concatenation operator succeed.
        target.attr = {'linkflags': None, 'extra_linkflags': []}
        # Layer that ``_cc_link`` consults for the linker family.
        toolchain = mock.Mock()
        toolchain.target_os = target_os
        target.blade = mock.Mock()
        target.blade.get_build_toolchain.return_value = toolchain
        # Capture warnings; ``self.warning`` in CcTarget normally prefixes the
        # target name, but we only care about the message text here.
        target.warnings = []
        target.warning = target.warnings.append
        # Capture the call to ``generate_build`` so we can inspect the
        # ``variables['extra_linkflags']`` blob that would land in ninja.
        target.generate_build_calls = []

        def fake_generate_build(rule, output, **kwargs):
            target.generate_build_calls.append(
                {'rule': rule, 'output': output, **kwargs})

        target.generate_build = fake_generate_build
        return target

    def _link_call(self, target, rule):
        """Return the single generate_build call for the given link rule."""
        matches = [c for c in target.generate_build_calls if c['rule'] == rule]
        self.assertEqual(1, len(matches),
                         f'expected one {rule!r} edge, got: {target.generate_build_calls!r}')
        return matches[0]

    def _extra_linkflags(self, target, rule):
        return self._link_call(target, rule).get(
            'variables', {}).get('extra_linkflags', '')

    def test_version_script_translates_to_exports_list_on_darwin(self):
        # On Darwin the GNU-ld --version-script doesn't pass through; it gets
        # filtered through cc_macos_exports into a plain symbol list that ld64
        # actually understands.
        target = self._target_with_toolchain('darwin')
        target._cc_link('libfoo.dylib', 'solink',
                        objs=['a.o', 'b.o'], deps=[], sys_libs=[],
                        version_scripts=['libfoo.map'])
        # 1) A cc_macos_exports edge is emitted, fed by the objs and gated by
        #    the map; its output becomes the link's implicit dep.
        exports_edge = self._link_call(target, 'cc_macos_exports')
        self.assertEqual(
            exports_edge['output'], 'libfoo.dylib.exported_symbols_list')
        self.assertEqual(['a.o', 'b.o'], exports_edge['inputs'])
        self.assertEqual(['libfoo.map'], exports_edge['implicit_deps'])
        self.assertEqual('libfoo.map',
                         exports_edge['variables']['export_map'])
        # 2) The link command uses ld64's -exported_symbols_list (the
        #    --version-script spelling that ld64 rejects is gone).
        link_flags = self._extra_linkflags(target, 'solink')
        self.assertIn(
            '-Wl,-exported_symbols_list,libfoo.dylib.exported_symbols_list',
            link_flags)
        self.assertNotIn('--version-script', link_flags)
        # 3) No warnings: the map is fully honored on Darwin.
        self.assertEqual([], target.warnings)

    def test_version_script_emitted_on_linux(self):
        target = self._target_with_toolchain('linux')
        target._cc_link('libfoo.so', 'solink', objs=[], deps=[], sys_libs=[],
                        version_scripts=['libfoo.map'])
        self.assertIn('--version-script=libfoo.map',
                      self._extra_linkflags(target, 'solink'))
        self.assertEqual([], target.warnings)
        # No cc_macos_exports edge on Linux.
        self.assertNotIn(
            'cc_macos_exports',
            [c['rule'] for c in target.generate_build_calls])

    def test_linker_script_dropped_on_darwin(self):
        # linker_script remains in the "warn and drop" state -- there's no
        # equivalent in ld64 we can translate to, and users should reach for
        # __attribute__((section(...))) etc. instead.
        target = self._target_with_toolchain('darwin')
        target._cc_link('foo', 'link', objs=[], deps=[], sys_libs=[],
                        linker_scripts=['layout.lds'])
        flags = self._extra_linkflags(target, 'link')
        self.assertNotIn('-T', flags)
        self.assertNotIn('layout.lds', flags)
        self.assertTrue(
            any('macOS' in w and 'linker_script' in w
                for w in target.warnings),
            f'expected a linker_script/macOS warning, got: {target.warnings!r}')

    def test_linker_script_emitted_on_linux(self):
        target = self._target_with_toolchain('linux')
        target._cc_link('foo', 'link', objs=[], deps=[], sys_libs=[],
                        linker_scripts=['layout.lds'])
        self.assertIn('-T layout.lds',
                      self._extra_linkflags(target, 'link'))
        self.assertEqual([], target.warnings)


class CheckIncorrectNoWarningTest(unittest.TestCase):
    """Cover ``CcTarget._check_incorrect_no_warning`` and its config knob.

    ``warning='no'`` is legitimate only for third-party code; using it
    elsewhere silences real warnings. The set of allowed path keywords is
    configurable via ``cc_config.no_warning_allowed_paths`` (issues #646,
    #805) -- these tests pin both the gate and the config plumbing.
    """

    def _target(self, srcs, path):
        target = _bare_cc_target()
        target.srcs = srcs
        target.path = path
        target.warning = mock.Mock()
        return target

    def _check(self, target, warning, allowed):
        with mock.patch.object(cc_targets.config, 'get_item',
                               return_value=allowed) as get_item:
            target._check_incorrect_no_warning(warning)
        return get_item

    def test_no_warning_outside_allowed_paths_warns(self):
        target = self._target(['src/foo.cc'], 'src')
        self._check(target, 'no', ['thirdparty'])
        target.warning.assert_called_once()

    def test_no_warning_under_allowed_path_is_silent(self):
        target = self._target(['thirdparty/zlib/z.c'], 'thirdparty/zlib')
        self._check(target, 'no', ['thirdparty'])
        target.warning.assert_not_called()

    def test_custom_allowed_path_is_honoured(self):
        # A path the default would reject is accepted once configured.
        target = self._target(['vendor/lib/a.cc'], 'vendor/lib')
        self._check(target, 'no', ['vendor'])
        target.warning.assert_not_called()

    def test_warning_other_than_no_short_circuits(self):
        # Must return before consulting the config at all.
        target = self._target(['src/foo.cc'], 'src')
        get_item = self._check(target, 'yes', ['thirdparty'])
        get_item.assert_not_called()
        target.warning.assert_not_called()

    def test_empty_srcs_short_circuits(self):
        target = self._target([], 'src')
        get_item = self._check(target, 'no', ['thirdparty'])
        get_item.assert_not_called()
        target.warning.assert_not_called()


class WindowsExportLinkInputsTest(unittest.TestCase):
    """cc_binary Windows symbol export (#1201): on MSVC an `export_map` drives a
    COMDAT-filtered `.def` (cc_windef) + /DEF + /IMPLIB so the exe exports the
    selected symbols and emits an import library dependents can link."""

    def _binary(self, export_map):
        t = cc_targets.CcBinary.__new__(cc_targets.CcBinary)
        t.name = 'host'
        t.attr = {'export_map_fullpath': export_map}
        t.data = {}
        self.tc = mock.Mock()
        self.tc.static_lib_suffix = '.lib'
        self.tc.DYNAMIC_LIB_LABEL = 'so'
        t._target_file_path = lambda p: os.path.join('BD/host', p)
        t.target_files = {}
        t._add_target_file = lambda label, path: t.target_files.__setitem__(label, path)
        t.generate_build_calls = []
        t.generate_build = lambda rule, output, **kw: t.generate_build_calls.append(
            {'rule': rule, 'output': output, **kw})
        return t

    def _call(self, t, objs=('a.o',), order_only=()):
        return t._windows_export_link_inputs(self.tc, self.flags, list(objs), list(order_only))

    def setUp(self):
        self.flags = ['/SUBSYSTEM:CONSOLE']

    def test_no_export_map_is_noop(self):
        t = self._binary([])
        self.assertEqual(([], None), self._call(t))
        self.assertEqual(['/SUBSYSTEM:CONSOLE'], self.flags)
        self.assertEqual([], t.generate_build_calls)

    def test_export_map_generates_def_and_implib(self):
        t = self._binary(['api.map'])
        deps, outs = self._call(t, objs=['a.o', 'b.o'])
        def_file = os.path.join('BD/host', 'host.def')
        implib = os.path.join('BD/host', 'host.lib')
        # cc_windef builds the filtered .def from the objs, gated by the map.
        windef = [c for c in t.generate_build_calls if c['rule'] == 'cc_windef']
        self.assertEqual(1, len(windef))
        self.assertEqual(def_file, windef[0]['output'])
        self.assertEqual(['a.o', 'b.o'], windef[0]['inputs'])
        self.assertEqual('--export_map=api.map', windef[0]['variables']['defflags'])
        # link gets /DEF + /IMPLIB; the def is an input, the implib an output.
        self.assertIn('/DEF:%s' % def_file, self.flags)
        self.assertIn('/IMPLIB:%s' % implib, self.flags)
        self.assertEqual(([def_file], [implib]), (deps, outs))
        self.assertEqual(implib, t.target_files['so'])     # dependents can link it
        self.assertEqual(implib, t.data['windows_implib'])


if __name__ == '__main__':
    unittest.main()
