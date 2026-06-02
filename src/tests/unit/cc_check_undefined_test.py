#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for the cc_check_undefined nm-based static check (issue #1225).

"""Unit tests for cc_check_undefined and the system_symbols module that
feeds its baseline.
"""

import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402
from blade import builtin_tools  # noqa: E402
from blade import system_symbols  # noqa: E402


# ----------------------------------------------------------------------------
# Config surface (cc_library_config.check_undefined / allow_undefined)
# ----------------------------------------------------------------------------


class CheckUndefinedConfigDefaultsTest(unittest.TestCase):
    """Template defaults for the new options."""

    def setUp(self):
        self._template = config._CONFIG_TEMPLATE['cc_library_config']

    def test_check_undefined_defaults_true(self):
        self.assertTrue(self._template['check_undefined'])

    def test_allow_undefined_defaults_empty_list(self):
        self.assertEqual(self._template['allow_undefined'], [])


class CheckUndefinedConfigValidationTest(unittest.TestCase):
    """cc_library_config: regex compile-validation for allow_undefined."""

    def setUp(self):
        self._bc = config._blade_config
        self._saved = dict(self._bc.config)

    def tearDown(self):
        self._bc.config = self._saved

    def _call(self, **kwargs):
        warnings, errors = [], []
        with mock.patch.object(self._bc, 'warning', side_effect=warnings.append), \
             mock.patch.object(self._bc, 'error', side_effect=errors.append):
            config.cc_library_config(**kwargs)
        return warnings, errors

    def test_empty_allow_undefined_accepted(self):
        _, errors = self._call(allow_undefined=[])
        self.assertEqual(errors, [])

    def test_valid_regex_patterns_accepted(self):
        _, errors = self._call(allow_undefined=[r'_main', r'_ZN5myapp.*', r'_ZThn\d+_.*'])
        self.assertEqual(errors, [])

    def test_invalid_regex_errors_at_config_time(self):
        _, errors = self._call(allow_undefined=['[unclosed'])
        self.assertEqual(len(errors), 1)
        self.assertIn('invalid regex', errors[0])

    def test_non_string_entry_errors(self):
        _, errors = self._call(allow_undefined=[123])
        self.assertEqual(len(errors), 1)
        self.assertIn('non-string', errors[0])

    def test_non_list_value_errors(self):
        _, errors = self._call(allow_undefined='_main')
        self.assertEqual(len(errors), 1)
        self.assertIn('must be a list', errors[0])

    def test_check_undefined_bool_accepted(self):
        _, errors = self._call(check_undefined=False)
        self.assertEqual(errors, [])


# ----------------------------------------------------------------------------
# Residual baseline (small set of compiler-injected names not in any lib)
# ----------------------------------------------------------------------------


class ResidualBaselineTest(unittest.TestCase):
    """The residual baseline now only covers compiler-emitted symbols that
    don't live in any system library (typeinfo / vtable / guard variables /
    TLV stubs / __dso_handle). Library symbols are enumerated from the
    actual installed libs by ``system_symbols`` and shouldn't appear here.
    """

    @classmethod
    def setUpClass(cls):
        cls.patterns = builtin_tools._check_undefined_compile_baseline()

    def _allowed(self, name):
        return any(p.fullmatch(name) for p in self.patterns)

    def test_dso_handle(self):
        for n in ('__dso_handle', '___dso_handle'):
            self.assertTrue(self._allowed(n), n)

    def test_operator_new_delete_mangled(self):
        for n in ('_Znwm', '__Znwm', '_Znam', '__Znam',
                  '_ZdlPv', '__ZdlPv', '_ZdaPv', '__ZdaPv',
                  '_ZdlPvm', '__ZdlPvm'):
            self.assertTrue(self._allowed(n), n)

    def test_typeinfo_vtable_guard(self):
        for n in ('_ZTIb', '__ZTIb',          # typeinfo for bool
                  '_ZTSi', '__ZTSi',          # typeinfo name for int
                  '_ZTV1A', '__ZTV1A',        # vtable for A
                  '_ZTT1A', '__ZTT1A',        # VTT for A
                  '_ZGVN5myapp1xE'):           # guard variable for myapp::x
            self.assertTrue(self._allowed(n), n)

    def test_tlv_stubs(self):
        for n in ('_tlv_bootstrap', '__tlv_atexit', '___tlv_bootstrap'):
            self.assertTrue(self._allowed(n), n)

    def test_user_namespace_symbols_not_matched(self):
        """User code (now including libc functions like _malloc) must NOT
        match the residual baseline — those come from real lib enumeration."""
        for n in ('_ZN5myapp3fooEv', '__ZN5myapp3fooEv',
                  '_my_custom_symbol', 'plain_c_symbol',
                  '_malloc', '_pthread_create', '_strlen'):
            self.assertFalse(self._allowed(n), n)


# ----------------------------------------------------------------------------
# nm parser
# ----------------------------------------------------------------------------


class NmExtractTest(unittest.TestCase):
    """Test the per-archive nm output parser used at check time."""

    def test_parse_undefined_and_defined(self):
        fake_nm_output = (
            b'__ZTV1A T 100 0\n'
            b'foo T 200 0\n'
            b'bar U 0 0\n'
            b'_local t 300 0\n'   # lowercase t = local, ignore
            b'weak_undef_sym w 0 0\n'   # lowercase w = weak undefined, ignore
            b'weak_undef_obj v 0 0\n'   # lowercase v = weak undefined, ignore
            b'weak_def_sym W 500 0\n'   # uppercase W = weak defined, KEEP
            b'weak_def_obj V 600 0\n'   # uppercase V = weak defined, KEEP
            b'unique_global u 700 5\n'  # lowercase u = GNU unique global, KEEP
            b'baz D 400 0\n')
        with mock.patch.object(subprocess, 'check_output', return_value=fake_nm_output):
            undef, defd = builtin_tools._nm_extract_externals('/fake/lib.a')
        self.assertEqual(undef, {'bar'})
        self.assertEqual(defd, {'__ZTV1A', 'foo', 'baz',
                                'weak_def_sym', 'weak_def_obj',
                                'unique_global'})

    def test_archive_header_lines_skipped(self):
        fake = (b'lib.a[foo.o]:\n'
                b'foo T 100 0\n'
                b'lib.a[bar.o]:\n'
                b'bar U 0 0\n')
        with mock.patch.object(subprocess, 'check_output', return_value=fake):
            undef, defd = builtin_tools._nm_extract_externals('/fake/lib.a')
        self.assertEqual(undef, {'bar'})
        self.assertEqual(defd, {'foo'})

    def test_nm_failure_returns_empty_with_warning(self):
        from blade import console
        with mock.patch.object(subprocess, 'check_output',
                               side_effect=subprocess.CalledProcessError(1, 'nm')), \
             mock.patch.object(console, 'warning'):
            undef, defd = builtin_tools._nm_extract_externals('/fake/lib.a')
        self.assertEqual(undef, set())
        self.assertEqual(defd, set())


# ----------------------------------------------------------------------------
# system_symbols: cache validity, tbd parser, end-to-end ensure_cache
# ----------------------------------------------------------------------------


class CacheValidityTest(unittest.TestCase):
    """Cache invalidates on (mtime, size) mismatch of the source library."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write_source(self, name, content):
        path = os.path.join(self._tmpdir, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return path

    def test_cache_valid_when_unchanged(self):
        src = self._write_source('libfoo.dylib', 'fake content')
        cache = os.path.join(self._tmpdir, 'foo.syms')
        system_symbols._write_cache(cache, 'foo', src, {'sym_a', 'sym_b'})
        self.assertTrue(system_symbols._is_cache_valid(cache, 'foo', src))

    def test_cache_invalid_when_source_size_changes(self):
        src = self._write_source('libfoo.dylib', 'fake')
        cache = os.path.join(self._tmpdir, 'foo.syms')
        system_symbols._write_cache(cache, 'foo', src, {'sym_a'})
        # Append to bump size.
        with open(src, 'a', encoding='utf-8') as f:
            f.write('more')
        self.assertFalse(system_symbols._is_cache_valid(cache, 'foo', src))

    def test_cache_invalid_when_alias_differs(self):
        src = self._write_source('libfoo.dylib', 'fake')
        cache = os.path.join(self._tmpdir, 'foo.syms')
        system_symbols._write_cache(cache, 'foo', src, {'sym_a'})
        self.assertFalse(system_symbols._is_cache_valid(cache, 'bar', src))

    def test_cache_invalid_when_source_missing(self):
        src = self._write_source('libfoo.dylib', 'fake')
        cache = os.path.join(self._tmpdir, 'foo.syms')
        system_symbols._write_cache(cache, 'foo', src, {'sym_a'})
        os.unlink(src)
        self.assertFalse(system_symbols._is_cache_valid(cache, 'foo', src))

    def test_cache_invalid_when_header_truncated(self):
        cache = os.path.join(self._tmpdir, 'foo.syms')
        with open(cache, 'w', encoding='utf-8') as f:
            f.write('# blade system-symbols cache v1\n# alias: foo\n')  # missing rest
        self.assertFalse(system_symbols._is_cache_valid(cache, 'foo', '/anywhere'))


class TbdParserTest(unittest.TestCase):
    """Apple ``.tbd`` text stub parser. Skips ``re-exports:`` (file paths),
    handles multi-line ``symbols: [ ... ]`` blocks, expands Objective-C class
    entries to the ``_OBJC_CLASS_$_`` / ``_OBJC_METACLASS_$_`` linker forms,
    and reads all embedded YAML documents (libSystem-style umbrella tbds)."""

    def _write(self, content):
        f = tempfile.NamedTemporaryFile('w', suffix='.tbd', delete=False)
        self.addCleanup(os.unlink, f.name)
        f.write(content)
        f.close()
        return f.name

    def test_single_line_symbols_block(self):
        path = self._write('symbols: [ _foo, _bar ]\n')
        syms = system_symbols._tbd_extract_symbols(path)
        self.assertEqual(syms, {'_foo', '_bar'})

    def test_multi_line_symbols_block(self):
        path = self._write(
            'exports:\n'
            '  - targets: [ arm64-macos ]\n'
            '    symbols: [ _foo, _bar,\n'
            '               _baz, _quux ]\n')
        syms = system_symbols._tbd_extract_symbols(path)
        self.assertEqual(syms, {'_foo', '_bar', '_baz', '_quux'})

    def test_multi_document_tbd(self):
        path = self._write(
            '--- !tapi-tbd\n'
            'install-name: /usr/lib/libSystem.B.dylib\n'
            'exports:\n'
            '  - symbols: [ _sysfn ]\n'
            '--- !tapi-tbd\n'
            'install-name: /usr/lib/system/libsystem_pthread.dylib\n'
            'exports:\n'
            '  - symbols: [ _pthread_create, _pthread_self ]\n'
            '--- !tapi-tbd\n'
            'install-name: /usr/lib/system/libsystem_m.dylib\n'
            'exports:\n'
            '  - symbols: [ _sin, _cos ]\n')
        syms = system_symbols._tbd_extract_symbols(path)
        self.assertEqual(syms, {'_sysfn', '_pthread_create', '_pthread_self',
                                '_sin', '_cos'})

    def test_objc_classes_expanded_to_link_symbols(self):
        path = self._write(
            'exports:\n'
            '  - objc-classes: [ NSObject, NSString ]\n')
        syms = system_symbols._tbd_extract_symbols(path)
        self.assertIn('_OBJC_CLASS_$_NSObject', syms)
        self.assertIn('_OBJC_METACLASS_$_NSObject', syms)
        self.assertIn('_OBJC_CLASS_$_NSString', syms)
        self.assertIn('_OBJC_METACLASS_$_NSString', syms)

    def test_re_exports_section_ignored(self):
        # re-exports lists file paths to other dylibs, not symbols.
        path = self._write(
            're-exports:\n'
            '  - libraries: [ "/usr/lib/system/libsystem_c.dylib" ]\n')
        syms = system_symbols._tbd_extract_symbols(path)
        self.assertEqual(syms, set())

    def test_quoted_symbol_names(self):
        path = self._write('symbols: [ "_foo", "_bar with weird $name" ]\n')
        syms = system_symbols._tbd_extract_symbols(path)
        self.assertEqual(syms, {'_foo', '_bar with weird $name'})


class ResolveLibPathLinkerScriptTest(unittest.TestCase):
    """Linux glibc ships libc.so / libpthread.so etc. as GNU-ld linker
    scripts rather than real ELFs; ``cc -print-file-name`` happily returns
    them. resolve_lib_path must sniff and follow them to the real .so."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _write(self, name, content, mode='w'):
        path = os.path.join(self._tmpdir, name)
        with open(path, mode) as f:
            f.write(content)
        return path

    def test_looks_like_binary_lib_elf(self):
        path = self._write('lib.so', b'\x7fELF\x02\x01\x01\x00', mode='wb')
        self.assertTrue(system_symbols._looks_like_binary_lib(path))

    def test_looks_like_binary_lib_macho(self):
        path = self._write('lib.dylib', b'\xcf\xfa\xed\xfe\x00\x00\x00\x00', mode='wb')
        self.assertTrue(system_symbols._looks_like_binary_lib(path))

    def test_looks_like_binary_lib_ar(self):
        path = self._write('lib.a', b'!<arch>\n', mode='wb')
        self.assertTrue(system_symbols._looks_like_binary_lib(path))

    def test_looks_like_binary_lib_pe(self):
        path = self._write('lib.lib', b'MZ\x90\x00', mode='wb')
        self.assertTrue(system_symbols._looks_like_binary_lib(path))

    def test_looks_like_binary_lib_tbd_accepted(self):
        # .tbd is YAML text but our caller handles it specially.
        path = self._write('libSystem.tbd', '--- !tapi-tbd\n')
        self.assertTrue(system_symbols._looks_like_binary_lib(path))

    def test_looks_like_binary_lib_rejects_linker_script(self):
        path = self._write('libc.so',
                           'GROUP ( /lib/libc.so.6 AS_NEEDED ( /lib/ld.so ) )\n')
        self.assertFalse(system_symbols._looks_like_binary_lib(path))

    def test_follow_linker_script_returns_all_members(self):
        # Glibc's linker script bundles libc.so.6 + libc_nonshared.a.
        # Some symbols (__stack_chk_fail) only live in the .a -- we need
        # both. Realpath both sides for macOS /tmp -> /private/tmp.
        target_so = self._write('libc.so.6', b'\x7fELF\x02\x01\x01\x00', mode='wb')
        target_a = self._write('libc_nonshared.a', b'!<arch>\n', mode='wb')
        script = self._write('libc.so',
                             'GROUP ( %s %s AS_NEEDED ( /lib/ld.so ) )\n' % (target_so, target_a))
        self.assertEqual(system_symbols._follow_linker_script(script),
                         [os.path.realpath(target_so), os.path.realpath(target_a)])

    def test_follow_linker_script_returns_single_archive(self):
        target = self._write('libfoo.a', b'!<arch>\n', mode='wb')
        script = self._write('libfoo.so', 'INPUT ( %s )\n' % target)
        self.assertEqual(system_symbols._follow_linker_script(script),
                         [os.path.realpath(target)])

    def test_follow_linker_script_returns_empty_for_non_script(self):
        path = self._write('libfoo.so', b'\x7fELF\x02\x01\x01\x00', mode='wb')
        self.assertEqual(system_symbols._follow_linker_script(path), [])

    def test_follow_linker_script_ignores_relative_paths(self):
        script = self._write('libfoo.so', 'GROUP ( ./libfoo.so.6 )\n')
        self.assertEqual(system_symbols._follow_linker_script(script), [])


class EnsureCacheTest(unittest.TestCase):
    """End-to-end ensure_cache: resolves a fake .tbd via the macOS SDK
    fallback path (mocked) and writes a valid cache file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.addCleanup(self._cleanup)
        # Build a fake toolchain object satisfying the attributes the
        # module touches: cc and target_os.
        self.tc = mock.Mock()
        self.tc.cc = 'gcc'
        self.tc.target_os = 'linux'

    def _cleanup(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_writes_cache_with_header_and_symbols(self):
        fake_lib = os.path.join(self._tmpdir, 'libfoo.so')
        with open(fake_lib, 'w', encoding='utf-8') as f:
            f.write('fake')
        with mock.patch.object(system_symbols, 'resolve_lib_paths',
                               return_value=[fake_lib]), \
             mock.patch.object(system_symbols, '_nm_defined_externals',
                               return_value={'_foo', '_bar'}):
            cache = system_symbols.ensure_cache(self.tc, 'foo', self._tmpdir)
        assert cache is not None  # narrows type for pyright + acts as assertion
        with open(cache, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('# alias: foo', content)
        self.assertIn('# source: %s' % fake_lib, content)
        self.assertIn('_bar', content)
        self.assertIn('_foo', content)

    def test_reuses_cache_when_source_unchanged(self):
        fake_lib = os.path.join(self._tmpdir, 'libfoo.so')
        with open(fake_lib, 'w', encoding='utf-8') as f:
            f.write('fake')
        with mock.patch.object(system_symbols, 'resolve_lib_paths',
                               return_value=[fake_lib]), \
             mock.patch.object(system_symbols, '_nm_defined_externals',
                               return_value={'_foo'}) as nm:
            system_symbols.ensure_cache(self.tc, 'foo', self._tmpdir)
            system_symbols.ensure_cache(self.tc, 'foo', self._tmpdir)
            # Second call should reuse cache and skip nm.
            self.assertEqual(nm.call_count, 1)

    def test_returns_none_when_lib_unresolvable(self):
        with mock.patch.object(system_symbols, 'resolve_lib_paths',
                               return_value=[]):
            cache = system_symbols.ensure_cache(self.tc, 'no_such_lib', self._tmpdir)
        self.assertIsNone(cache)


# ----------------------------------------------------------------------------
# End-to-end check tool with mocked archives
# ----------------------------------------------------------------------------


class CheckUndefinedDiffTest(unittest.TestCase):
    """Run generate_cc_check_undefined with mocked nm output and synthetic
    .syms files. Verifies the resolution order:
       target undefined  -  target defined  (intra-archive)
                         -  defined externals from each dep .a
                         -  symbols from each .syms cache
                         -  residual baseline + user allowlist
       = error iff non-empty.
    """

    def _run(self, target_syms, dep_syms_list=(), sys_sym_sets=(),
             allow_patterns=()):
        with tempfile.TemporaryDirectory() as tmp:
            def write_archive_syms(name, undef, defd):
                """Write a per-archive .syms file (#U + #D sections).

                Format produced by ``generate_cc_emit_syms``; consumed by
                ``_read_archive_syms`` inside the check tool.
                """
                p = os.path.join(tmp, name + '.syms')
                with open(p, 'w', encoding='utf-8') as f:
                    f.write('# blade archive-symbols cache v1\n')
                    f.write('# archive: %s\n' % name)
                    f.write('#U\n')
                    for s in sorted(undef):
                        f.write(s + '\n')
                    f.write('#D\n')
                    for s in sorted(defd):
                        f.write(s + '\n')
                return p

            result = os.path.join(tmp, 'result')
            allow_file = os.path.join(tmp, 'allow')
            with open(allow_file, 'w', encoding='utf-8') as f:
                for p in allow_patterns:
                    f.write(p + '\n')

            args = [result, write_archive_syms('target', *target_syms)]
            for i, ds in enumerate(dep_syms_list):
                args.append(write_archive_syms('dep%d' % i, *ds))
            # Materialize each system sym set as a real .syms cache file
            # (system caches are defined-only; ``_read_archive_syms`` handles
            # the legacy no-#U-section shape automatically).
            for i, sset in enumerate(sys_sym_sets):
                p = os.path.join(tmp, 'lib%d.syms' % i)
                with open(p, 'w', encoding='utf-8') as f:
                    f.write('# blade system-symbols cache v1\n')
                    f.write('# alias: lib%d\n' % i)
                    f.write('# source: /fake\n')
                    f.write('# mtime: 0\n')
                    f.write('# size: 0\n')
                    for s in sset:
                        f.write(s + '\n')
                args.append(p)

            rc = builtin_tools.generate_cc_check_undefined(
                args, **{'allow-file': allow_file, 'target-label': 'foo:bar'})
            exists = os.path.exists(result)
        return rc, exists

    def test_no_undefined_succeeds(self):
        rc, ok = self._run(target_syms=(set(), {'foo'}))
        self.assertIsNone(rc)
        self.assertTrue(ok)

    def test_intra_archive_resolution(self):
        rc, ok = self._run(target_syms=({'foo'}, {'foo'}))
        self.assertIsNone(rc)
        self.assertTrue(ok)

    def test_dep_archive_resolves(self):
        rc, ok = self._run(target_syms=({'bar'}, set()),
                           dep_syms_list=[(set(), {'bar'})])
        self.assertIsNone(rc)
        self.assertTrue(ok)

    def test_truly_missing_dep_fails(self):
        rc, ok = self._run(target_syms=({'wholly_missing'}, set()),
                           dep_syms_list=[(set(), {'something_else'})])
        self.assertEqual(rc, 1)
        self.assertFalse(ok)

    def test_system_lib_resolves(self):
        rc, ok = self._run(target_syms=({'_pthread_create', '_malloc'}, set()),
                           sys_sym_sets=[{'_pthread_create', '_malloc', '_strlen'}])
        self.assertIsNone(rc)
        self.assertTrue(ok)

    def test_residual_baseline_resolves_typeinfo(self):
        # _ZTIb (typeinfo for bool) is in the residual baseline (not in any lib).
        rc, _ = self._run(target_syms=({'_ZTIb', '__ZTIb'}, set()))
        self.assertIsNone(rc)

    def test_residual_baseline_resolves_linker_injected_stubs(self):
        # ld-linux.so injects __tls_get_addr (dynamic TLS) and macOS dyld
        # injects _tlv_bootstrap. Both are baselined since user code can't
        # declare a dep on the runtime loader.
        rc, _ = self._run(target_syms=(
            {'__tls_get_addr', '__tls_get_offset', '_tlv_bootstrap'}, set()))
        self.assertIsNone(rc)

    def test_user_allow_pattern_resolves(self):
        rc, _ = self._run(target_syms=({'_my_legacy_symbol'}, set()),
                          allow_patterns=[r'_my_legacy_\w+'])
        self.assertIsNone(rc)

    def test_unrelated_user_pattern_does_not_help(self):
        rc, _ = self._run(target_syms=({'_real_missing'}, set()),
                          allow_patterns=[r'_my_legacy_\w+'])
        self.assertEqual(rc, 1)


if __name__ == '__main__':
    unittest.main()
