#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for _detect_default_linked_libs (PR #1233 follow-up).

"""Tests for the ``-### -x c++`` driver-output parser that supplements
``GccToolChain.default_linked_libs`` with toolchain-specific entries
the hardcoded list might miss.
"""

import os
import subprocess
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import toolchain  # noqa: E402
from blade.toolchain import _detect_default_linked_libs  # noqa: E402
from blade.toolchain import _classify_msvc_directive  # noqa: E402
from blade.toolchain import _detect_default_linked_libs_msvc  # noqa: E402


def _fake_run(stderr_text):
    """Build a ``subprocess.run`` replacement that returns the given stderr."""
    def runner(*args, **kwargs):
        m = mock.Mock()
        m.stderr = stderr_text
        m.stdout = ''
        m.returncode = 0
        return m
    return runner


class DetectDefaultLinkedLibsTest(unittest.TestCase):
    """Cover the parser's handling of real driver output shapes."""

    def _run_with(self, stderr_text):
        """Invoke the detector with a patched subprocess.run."""
        with mock.patch.object(subprocess, 'run',
                               side_effect=_fake_run(stderr_text)):
            return _detect_default_linked_libs('cxx-stub')

    # ---- macOS clang shape ----

    def test_macos_clang_link_line(self):
        """Apple Clang quotes each argument; the linker is ``ld`` from
        the Xcode toolchain. ``-lto_library`` is a flag (selects the LTO
        plugin), not a library."""
        stderr = (
            ' "/Applications/Xcode.app/Contents/Developer/Toolchains/'
            'XcodeDefault.xctoolchain/usr/bin/clang" "-cc1" ...\n'
            ' "/Applications/Xcode.app/Contents/Developer/Toolchains/'
            'XcodeDefault.xctoolchain/usr/bin/ld" "-demangle" '
            '"-lto_library" "/Applications/.../libLTO.dylib" '
            '"-dynamic" "-arch" "arm64" "-o" "/tmp/out" "-lc++" '
            '"-lSystem"\n'
        )
        self.assertEqual(self._run_with(stderr), ('c++', 'System'))

    def test_macos_lto_library_filtered(self):
        """``-lto_library`` must not leak in as a library name, AND its
        following path argument must not be picked up as a direct-path
        library entry."""
        stderr = ' "/usr/bin/ld" "-lto_library" "/path/libLTO.dylib" "-lSystem"\n'
        self.assertEqual(self._run_with(stderr), ('System',))

    def test_macos_direct_path_compiler_rt(self):
        """Apple Clang always links compiler-rt as a direct path, not via
        ``-l``. Its symbols (compiler builtins, soft-float, atomics) need
        to land in the baseline. The detector picks it up alongside the
        ``-l`` aliases."""
        stderr = (
            ' "/usr/bin/ld" "-lto_library" "/path/libLTO.dylib" "-arch" '
            '"arm64" "-o" "/tmp/out" "/tmp/cc.o" "-lc++" "-lSystem" '
            '"/Applications/Xcode.app/.../libclang_rt.osx.a"\n'
        )
        self.assertEqual(
            self._run_with(stderr),
            ('c++', 'System',
             '/Applications/Xcode.app/.../libclang_rt.osx.a'),
        )

    def test_linux_gcc_plugin_arg_skipped(self):
        """GCC's link line contains ``-plugin /path/to/liblto_plugin.so``;
        the path is a tool plugin, NOT a default-linked library. The
        ``-plugin`` flag is in the skip-next-arg set so the plugin path
        is consumed without being misclassified."""
        stderr = (
            ' /usr/libexec/.../collect2 -plugin '
            '/usr/libexec/.../liblto_plugin.so -dynamic-linker '
            '/lib/ld-linux.so.2 /tmp/cc.o -lstdc++ -lm -lc\n'
        )
        self.assertEqual(self._run_with(stderr), ('stdc++', 'm', 'c'))

    def test_output_path_after_dash_o_skipped(self):
        """``-o /tmp/output`` must not pick up ``/tmp/output`` as a
        library entry (it doesn't end in a lib extension anyway, but
        the explicit skip is defense in depth)."""
        stderr = ' /usr/bin/ld -o /tmp/_blade_test.so -lc\n'
        # /tmp/_blade_test.so contains '.so' but it's the -o argument.
        self.assertEqual(self._run_with(stderr), ('c',))

    def test_compiled_user_object_not_picked_up(self):
        """The user's compiled .o (something like ``/tmp/cc<hash>.o``)
        is on the link line as a positional input. It ends in ``.o``
        so the direct-path filter excludes it."""
        stderr = ' /usr/bin/ld /tmp/ccABCDE.o -lc\n'
        self.assertEqual(self._run_with(stderr), ('c',))

    # ---- Linux GCC shape ----

    def test_linux_gcc_collect2_line(self):
        """GCC drivers invoke ``collect2`` (the link wrapper) with
        unquoted args. -lgcc appears twice (GCC's standard link-group
        convention); dedupe but preserve first-seen order."""
        stderr = (
            ' /usr/libexec/gcc/x86_64-linux-gnu/13/cc1plus ...\n'
            ' /usr/libexec/gcc/x86_64-linux-gnu/13/collect2 -plugin '
            '/usr/libexec/.../liblto_plugin.so --eh-frame-hdr '
            '-m elf_x86_64 -dynamic-linker /lib64/ld-linux-x86-64.so.2 '
            '/tmp/cc.o -lstdc++ -lm -lgcc_s -lgcc -lc -lgcc_s -lgcc\n'
        )
        self.assertEqual(self._run_with(stderr),
                         ('stdc++', 'm', 'gcc_s', 'gcc', 'c'))

    def test_linux_lld_link_line(self):
        """LLVM's lld is also detected (some setups use ``ld.lld``)."""
        stderr = ' /usr/bin/ld.lld -o /tmp/out /tmp/cc.o -lc++ -lc\n'
        self.assertEqual(self._run_with(stderr), ('c++', 'c'))

    # ---- Special / edge cases ----

    def test_literal_filename_l_form_skipped(self):
        """GNU ld's ``-l:libfoo.so.1`` resolves to a specific filename
        rather than a library alias; we can't represent it as a blade
        ``#alias`` so we skip it."""
        stderr = ' /usr/bin/ld -o /tmp/out -lc -l:libgcc_s.so.1\n'
        self.assertEqual(self._run_with(stderr), ('c',))

    def test_only_first_link_line_consumed(self):
        """Some drivers echo the command multiple times (e.g. a banner
        followed by the actual invocation). Take only the first link
        line that contains ``-l<name>`` tokens; ignore the rest."""
        stderr = (
            ' /usr/bin/ld -lFIRST -lSYS\n'
            ' /usr/bin/ld -lSECOND -lSYS\n'
        )
        self.assertEqual(self._run_with(stderr), ('FIRST', 'SYS'))

    def test_non_link_line_with_dash_l_substring_ignored(self):
        """Compiler-frontend lines often contain things like
        ``-disable-llvm-verifier`` -- the ``-l`` substring inside an
        identifier must not be misread as a library flag."""
        stderr = (
            ' /usr/bin/cc1 "-disable-llvm-verifier" "-mllvm" '
            '"-enable-linkonceodr-outlining"\n'
        )
        # No linker marker -> nothing extracted.
        self.assertEqual(self._run_with(stderr), ())

    def test_dash_l_alone_skipped(self):
        """A bare ``-l`` (no name) is malformed; ignore."""
        stderr = ' /usr/bin/ld -l -lSystem\n'
        self.assertEqual(self._run_with(stderr), ('System',))

    # ---- Failure modes ----

    def test_compiler_not_found_returns_empty(self):
        """If the driver isn't on PATH, the parser must not raise."""
        def boom(*args, **kwargs):
            raise FileNotFoundError(2, 'not found', args[0][0])
        with mock.patch.object(subprocess, 'run', side_effect=boom):
            self.assertEqual(_detect_default_linked_libs('no-such-cxx'), ())

    def test_timeout_returns_empty(self):
        """A hung driver must not block blade indefinitely."""
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd='cxx', timeout=15)
        with mock.patch.object(subprocess, 'run', side_effect=slow):
            self.assertEqual(_detect_default_linked_libs('cxx'), ())

    def test_no_link_line_returns_empty(self):
        """Driver output that contains no recognizable linker invocation
        (e.g. a syntax-error compile that never reached link) yields ()."""
        stderr = ' /usr/bin/cc1 "-cc1" "-E" "/dev/null"\n'
        self.assertEqual(self._run_with(stderr), ())

    def test_malformed_quoting_skipped(self):
        """A line that fails ``shlex.split`` (mismatched quotes) is
        skipped rather than crashing the detector."""
        stderr = (
            ' /usr/bin/ld "unclosed -lBAD\n'
            ' /usr/bin/ld -lGOOD\n'
        )
        # Mismatched quote on the first line -> skipped; the second
        # well-formed line provides the answer.
        self.assertEqual(self._run_with(stderr), ('GOOD',))


class GccToolChainDefaultLinkedLibsTest(unittest.TestCase):
    """Pin the union semantic: hardcoded as the floor, auto-detect as the
    supplement; novel extras appended after the hardcoded set."""

    def _tc(self, target_os, cxx='cxx-stub'):
        tc = toolchain.GccToolChain.__new__(toolchain.GccToolChain)
        tc._target = target_os
        tc.cxx = cxx
        return tc

    def test_union_no_extras(self):
        """When auto-detect is a strict subset of hardcoded, the result
        equals the hardcoded set (preserving its order)."""
        tc = self._tc('darwin')
        with mock.patch.object(toolchain, '_detect_default_linked_libs',
                               return_value=('c++', 'System')):
            self.assertEqual(tc.default_linked_libs,
                             ('System', 'c++', 'c++abi'))

    def test_union_with_extras(self):
        """Anything auto-detect finds that hardcoded missed gets
        appended after the hardcoded prefix."""
        tc = self._tc('linux')
        with mock.patch.object(toolchain, '_detect_default_linked_libs',
                               return_value=('stdc++', 'm', 'gcc_s', 'gcc', 'c')):
            self.assertEqual(tc.default_linked_libs,
                             # hardcoded: c, gcc_s, stdc++
                             # extras (new): m, gcc
                             ('c', 'gcc_s', 'stdc++', 'm', 'gcc'))

    def test_detection_empty_uses_hardcoded(self):
        """When auto-detect fails (returns ()), the hardcoded baseline
        alone is returned (the regression-safe path)."""
        tc = self._tc('linux')
        with mock.patch.object(toolchain, '_detect_default_linked_libs',
                               return_value=()):
            self.assertEqual(tc.default_linked_libs,
                             ('c', 'gcc_s', 'stdc++'))

    def test_result_cached_after_first_call(self):
        """The detector is ~100 ms; a per-instance cache ensures we run
        it at most once for the toolchain's lifetime."""
        tc = self._tc('linux')
        with mock.patch.object(toolchain, '_detect_default_linked_libs',
                               return_value=('extra1',)) as m:
            _ = tc.default_linked_libs
            _ = tc.default_linked_libs
            _ = tc.default_linked_libs
            self.assertEqual(m.call_count, 1)


class ClassifyMsvcDirectiveTest(unittest.TestCase):
    """The ``dumpbin /directives`` line classifier (MSVC analog of the
    GCC ``-l`` token classifier). Pure function -- runs on any platform."""

    def test_bare_defaultlib(self):
        self.assertEqual(_classify_msvc_directive('   /DEFAULTLIB:MSVCRT'), 'msvcrt')

    def test_quoted_with_lib_suffix(self):
        """Some directives are quoted and carry the ``.lib`` suffix; strip both."""
        self.assertEqual(_classify_msvc_directive('/DEFAULTLIB:"libcmt.lib"'), 'libcmt')

    def test_oldnames(self):
        self.assertEqual(_classify_msvc_directive('/DEFAULTLIB:OLDNAMES'), 'oldnames')

    def test_banner_line_ignored(self):
        self.assertIsNone(_classify_msvc_directive('   Linker Directives'))
        self.assertIsNone(_classify_msvc_directive('   ------------------'))

    def test_other_directives_ignored(self):
        """``/FAILIFMISMATCH`` and ``/merge`` are linker directives but not
        default libraries."""
        self.assertIsNone(_classify_msvc_directive(
            '/FAILIFMISMATCH:_MSC_VER=1900'))
        self.assertIsNone(_classify_msvc_directive('  /merge:.foo=.bar'))

    def test_blank_and_garbage(self):
        self.assertIsNone(_classify_msvc_directive(''))
        self.assertIsNone(_classify_msvc_directive('/DEFAULTLIB:'))
        self.assertIsNone(_classify_msvc_directive('/DEFAULTLIB:""'))


def _fake_msvc_run(compile_rc, directives_text):
    """Build a ``subprocess.run`` replacement: first call is the cl compile,
    second is ``dumpbin /directives``. (The ``/Fo`` object check is satisfied
    by patching ``os.path.isfile`` in the caller, so no real file is needed.)"""
    state = {'calls': 0}

    def runner(argv, *args, **kwargs):
        state['calls'] += 1
        m = mock.Mock()
        m.stderr = ''
        if state['calls'] == 1:               # cl compile
            m.returncode = compile_rc
            m.stdout = ''
        else:                                  # dumpbin /directives
            m.returncode = 0
            m.stdout = directives_text
        return m
    return runner


class DetectDefaultLinkedLibsMsvcTest(unittest.TestCase):
    """The end-to-end MSVC detector with cl/dumpbin mocked, so it runs on
    any platform."""

    _DIRECTIVES = (
        '\n'
        'Dump of file probe.obj\n\n'
        '   Linker Directives\n'
        '   -----------------\n'
        '   /DEFAULTLIB:MSVCRT\n'
        '   /DEFAULTLIB:OLDNAMES\n'
        '   /FAILIFMISMATCH:_CRT_STDIO_ISO_WIDE_SPECIFIERS=0\n'
    )

    def _run(self, runner):
        # Pretend dumpbin.exe sits next to cl.exe so resolution succeeds.
        with mock.patch('os.path.isfile', return_value=True), \
             mock.patch.object(subprocess, 'run', side_effect=runner):
            return _detect_default_linked_libs_msvc(r'C:\msvc\bin\cl.exe')

    def test_parses_defaultlib_directives(self):
        """Pulls the CRT + oldnames out of the directive dump; ignores the
        banner and ``/FAILIFMISMATCH``."""
        self.assertEqual(
            self._run(_fake_msvc_run(0, self._DIRECTIVES)),
            ('msvcrt', 'oldnames'))

    def test_compile_failure_returns_empty(self):
        self.assertEqual(self._run(_fake_msvc_run(2, '')), ())

    def test_no_directives_returns_empty(self):
        self.assertEqual(
            self._run(_fake_msvc_run(0, 'Dump of file probe.obj\n\nSummary\n')),
            ())

    def test_cl_not_found_returns_empty(self):
        def boom(*args, **kwargs):
            raise FileNotFoundError(2, 'not found')
        self.assertEqual(self._run(boom), ())

    def test_timeout_returns_empty(self):
        def slow(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd='cl', timeout=30)
        self.assertEqual(self._run(slow), ())

    def test_dumpbin_missing_returns_empty(self):
        """No dumpbin next to cl and none on PATH -> empty (no crash)."""
        with mock.patch('os.path.isfile', return_value=False), \
             mock.patch('shutil.which', return_value=None):
            self.assertEqual(
                _detect_default_linked_libs_msvc(r'C:\msvc\bin\cl.exe'), ())


class MsvcToolChainDefaultLinkedLibsTest(unittest.TestCase):
    """The union semantic on MSVC: hardcoded floor + detected extras."""

    # The hardcoded MSVC floor: C runtime + C++ stdlib (import + static) +
    # vcruntime + ucrt + kernel32.
    _FLOOR = ('msvcrt', 'msvcprt', 'libcpmt', 'vcruntime', 'ucrt', 'kernel32')

    def _tc(self, cc='cl-stub'):
        tc = toolchain.MsvcToolChain.__new__(toolchain.MsvcToolChain)
        tc.cc = cc
        # default_linked_libs passes the system include paths to the detector;
        # stub the installation state so get_system_include_paths() returns [].
        tc._msvc_path = None
        tc._sdk_path = None
        tc._sdk_ver = None
        return tc

    def test_union_appends_oldnames(self):
        """``oldnames`` (and any /MT ``libcmt``) is appended after the
        hardcoded prefix; the already-present ``msvcrt`` is not duplicated."""
        tc = self._tc()
        with mock.patch.object(toolchain, '_detect_default_linked_libs_msvc',
                               return_value=('msvcrt', 'oldnames')):
            self.assertEqual(tc.default_linked_libs, self._FLOOR + ('oldnames',))

    def test_detection_empty_uses_hardcoded(self):
        tc = self._tc()
        with mock.patch.object(toolchain, '_detect_default_linked_libs_msvc',
                               return_value=()):
            self.assertEqual(tc.default_linked_libs, self._FLOOR)

    def test_result_cached(self):
        tc = self._tc()
        with mock.patch.object(toolchain, '_detect_default_linked_libs_msvc',
                               return_value=('oldnames',)) as m:
            _ = tc.default_linked_libs
            _ = tc.default_linked_libs
            self.assertEqual(m.call_count, 1)


if __name__ == '__main__':
    unittest.main()
