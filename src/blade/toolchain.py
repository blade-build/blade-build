# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Chong Peng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
This module deals with the build toolchains.
"""


import os
import re
import subprocess
import sys
import tempfile

from blade import console
from blade.util import var_to_list, run_command


class BuildArchitecture:
    """
    The BuildArchitecture class manages architecture/bits configuration
    across various platforms/compilers combined with the input from
    command line.
    """
    _build_architecture = {
        'i386': {
            'alias': ['x86'],
            'bits': '32',
        },
        'x86_64': {
            'alias': ['amd64'],
            'bits': '64',
            'models': {
                '32': 'i386',
            }
        },
        'arm': {
            'alias': [],
            'bits': '32'
        },
        'aarch64': {
            'alias': ['arm64'],
            'bits': '64',
        },
        'ppc': {
            'alias': ['powerpc'],
            'bits': '32',
        },
        'ppc64': {
            'alias': ['powerpc64'],
            'bits': '64',
            'models': {
                '32': 'ppc',
            }
        },
        'ppc64le': {
            'alias': ['powerpc64le'],
            'bits': '64',
            'models': {
                '32': 'ppcle',
            }
        },
        'win32': {
            'alias': ['windows'],
            'bits': '32',
        },
        'win64': {
            'alias': ['windows64', 'x64'],
            'bits': '64',
            'models': {
                '32': 'win32',
            }
        },
    }

    @staticmethod
    def get_canonical_architecture(arch):
        """Get the canonical architecture from the specified arch."""
        canonical_arch = None
        for k, v in BuildArchitecture._build_architecture.items():
            if arch == k or arch in v['alias']:
                canonical_arch = k
                break
        return canonical_arch

    @staticmethod
    def get_architecture_bits(arch):
        """Get the architecture bits."""
        arch = BuildArchitecture.get_canonical_architecture(arch)
        if arch:
            return BuildArchitecture._build_architecture[arch]['bits']
        return None

    @staticmethod
    def get_model_architecture(arch, bits):
        """
        Get the model architecture from the specified arch and bits,
        such as, if arch is x86_64 and bits is '32', then the resulting
        model architecture is i386 which effectively means building
        32 bit target in a 64 bit environment.
        """
        arch = BuildArchitecture.get_canonical_architecture(arch)
        if arch:
            if bits == BuildArchitecture._build_architecture[arch]['bits']:
                return arch
            models = BuildArchitecture._build_architecture[arch].get('models')
            if models and bits in models:
                return models[bits]
        return None


class ToolChain:
    """Abstract base for toolchain implementations.

    Subclasses must set ``cc``, ``cxx``, ``ld``, ``ar``, ``cc_version``,
    and ``_cc_vendor`` during ``__init__``.
    """

    cc: str
    cxx: str
    ld: str
    ar: str
    cc_version: str
    _cc_vendor: str
    _kind: str
    _target: str

    # ------------------------------------------------------------------
    # Target file labels — internal keys used by cc_targets to register
    # and look up output files.  These are conventional and do not need
    # to match file extensions (e.g. MSVC keeps 'so' even though the
    # file ends in .dll).
    # ------------------------------------------------------------------
    STATIC_LIB_LABEL = 'a'
    # Per-archive symbol-set cache. Produced by the ``ccsyms`` ninja rule
    # alongside ``ar``; consumed by ``ccchkund`` and any other consumer that
    # needs to subtract the archive's defined externals from an undefined
    # set without re-running ``nm``. See issue #1225.
    STATIC_LIB_SYMS_LABEL = 'a.syms'
    DYNAMIC_LIB_LABEL = 'so'

    # ------------------------------------------------------------------
    # File naming properties — subclasses override to match their host OS.
    # ------------------------------------------------------------------

    @property
    def obj_suffix(self) -> str:
        """Object file suffix ('.o' / '.obj')."""
        return '.o'

    @property
    def static_lib_suffix(self) -> str:
        """Static library suffix ('.a' / '.lib')."""
        return '.a'

    @property
    def dynamic_lib_suffix(self) -> str:
        """Dynamic library suffix ('.so' / '.dll' / '.dylib')."""
        return '.so'

    @property
    def lib_prefix(self) -> str:
        """Library file name prefix ('lib' / '')."""
        return 'lib'

    @property
    def exe_suffix(self) -> str:
        """Executable file suffix ('' / '.exe')."""
        return ''

    @property
    def all_dynamic_lib_suffixes(self) -> tuple[str, ...]:
        """All dynamic-library suffixes across supported platforms.

        Used for diagnostic checks (e.g. detecting ambiguous cc_plugin names).
        """
        return ('.so', '.dylib', '.dll')

    def __init__(self):
        pass

    @property
    def target_os(self) -> str:
        """Target OS: ``'darwin'``, ``'linux'``, ``'windows'``."""
        return self._target

    @property
    def target_arch(self) -> str:
        """Target CPU architecture, e.g. ``'x86_64'`` or ``'aarch64'``."""
        cached = getattr(self, '_cached_target_arch', None)
        if cached is not None:
            return cached
        import re
        triple = self.get_cc_target_arch()
        result = ''
        if triple:
            m = re.match(r'^([^-]+)', triple)
            if m:
                result = BuildArchitecture.get_canonical_architecture(m.group(1)) or m.group(1)
        self._cached_target_arch = result
        return result

    def tool(self, key):
        """Return tool path for *key*, or ``None`` if not available.

        Supported keys: ``'cc'``, ``'cxx'``, ``'ld'``, ``'ar'``, ``'rc'``, ``'as'``.
        """
        return getattr(self, '_tools', {}).get(key)

    def _get_cc_version(self):
        version = ''
        returncode, stdout, stderr = run_command([self.cc, '-dumpversion'])
        if returncode == 0:
            version = stdout.strip()
        if not version:
            console.fatal('Failed to obtain cc toolchain.')
        return version

    def _detect_cc_vendor(self):
        """Identify the cc vendor by querying the compiler itself.

        Returns one of:
          - 'clang'        : LLVM/Clang (including Apple Clang that masquerades as
                             /usr/bin/gcc on macOS).
          - 'gcc'          : Real GNU GCC.
          - 'unknown'      : Detection failed. Callers treating a specific vendor
                             as a precondition should take the conservative path.

        Rationale: Relying on substring matching against the `cc` command name is
        unreliable. On macOS `gcc` is typically an alias for Apple Clang, and
        user-set CC/CXX may be an absolute path or a wrapper whose name reveals
        nothing about the underlying vendor.
        """
        returncode, stdout, stderr = run_command([self.cc, '--version'])
        if returncode != 0:
            return 'unknown'
        # `--version` output typically goes to stdout, but some wrappers emit on
        # stderr. Concatenate both and lower-case for robust matching.
        text = ((stdout or '') + '\n' + (stderr or '')).lower()
        if 'clang' in text:
            return 'clang'
        # Match 'gcc ', '(gcc)', 'gnu c' etc., but only after we've ruled out
        # clang (Apple Clang banner contains neither, upstream Clang shows
        # 'clang version ...').
        if 'gcc' in text or 'free software foundation' in text:
            return 'gcc'
        return 'unknown'

    _cc_target_arch_cache = None

    @classmethod
    def get_cc_target_arch(cls):
        """Get the cc target architecture (auto-detect from system compiler).

        The result is cached at the class level — ``gcc -dumpmachine`` is
        invariant for the lifetime of the process and forking the compiler
        per call was the dominant cost during BUILD-file loading.
        """
        if cls._cc_target_arch_cache is not None:
            return cls._cc_target_arch_cache
        import shutil
        cc = shutil.which('gcc') or 'gcc'
        returncode, stdout, stderr = run_command([cc, '-dumpmachine'])
        result = stdout.strip() if returncode == 0 else ''
        cls._cc_target_arch_cache = result
        return result

    def get_cc_commands(self):
        return self.cc, self.cxx, self.ld

    def get_cc(self):
        return self.cc

    def get_cc_version(self):
        return self.cc_version

    def get_ar(self):
        return self.ar

    def cc_is(self, vendor):
        """Return whether the detected cc vendor equals the given vendor.

        The comparison is an exact match against the result of
        `_detect_cc_vendor()` (one of 'clang', 'gcc', 'unknown').
        """
        return vendor == self._cc_vendor

    def object_file_of(self, src):
        """Return the object file path for a given source file."""
        return src + self.obj_suffix

    def static_library_name(self, name):
        """Return the static library output name for a given target name."""
        return self.lib_prefix + name + self.static_lib_suffix

    def dynamic_library_name(self, name):
        """Return the dynamic library output name for a given target name."""
        return self.lib_prefix + name + self.dynamic_lib_suffix

    def executable_file_name(self, name):
        """Return the executable output name for a given target name."""
        return name + self.exe_suffix

    @property
    def deps_style(self):
        """Return the ninja deps style: 'gcc' or 'msvc'."""
        return 'gcc'

    @property
    def uses_depfile(self):
        """Whether the compiler generates a .d depfile."""
        return True

    def get_system_include_paths(self):
        """Return system include paths, or empty list if not applicable."""
        return []

    def get_system_lib_paths(self):
        """Return system library search paths, or empty list if not applicable."""
        return []

    @property
    def default_linked_libs(self) -> 'tuple[str, ...]':
        """Library aliases the C/C++ driver links implicitly into every binary.

        Aliases are the same form blade uses in `#xxx` deps and in `-l<alias>`
        on the command line (e.g. ``c``, ``stdc++``, ``c++``, ``System``).
        Used by the ``check_undefined`` static check to seed the baseline of
        ambient symbols. Override per subclass; default is an empty tuple so
        toolchains that don't model this don't break callers.
        """
        return ()

    def filter_cc_flags(self, flag_list, language='c'):
        """Filter out the unrecognized compilation flags."""
        flag_list = var_to_list(flag_list)
        valid_flags, unrecognized_flags = [], []

        # Put compilation output into test.o instead of /dev/null
        # because the command line with '--coverage' below exit
        # with status 1 which makes '--coverage' unsupported
        # echo "int main() { return 0; }" | gcc -o /dev/null -c -x c --coverage - > /dev/null 2>&1
        fd, obj = tempfile.mkstemp('.o', 'filter_cc_flags_test')
        # Force C locale so we can reliably match the error messages below.
        env = os.environ.copy()
        env['LC_ALL'] = 'C'
        argv = [self.cc, '-o', obj, '-c', '-x', language, '-Werror'] + list(flag_list) + ['-']
        try:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env)
            _, stderr = proc.communicate(input=b'int main() { return 0; }\n')
            returncode = proc.returncode
            if isinstance(stderr, bytes):
                stderr = stderr.decode('utf-8', errors='replace')
        finally:
            try:
                # In case of error, the `.o` file will be deleted by the compiler
                os.remove(obj)
            except OSError:
                # Temp file may already be deleted by the compiler on error.
                pass
            os.close(fd)

        if returncode == 0:
            return flag_list
        for flag in flag_list:
            # Example error messages:
            #   clang: warning: unknown warning option '-Wzzz' [-Wunknown-warning-option]
            #   gcc:   gcc: error: unrecognized command line option '-Wxxx'
            if " option '%s'" % flag in stderr:
                unrecognized_flags.append(flag)
            else:
                valid_flags.append(flag)

        if unrecognized_flags:
            console.warning('config: Unrecognized {} flags: {}'.format(
                    language, ', '.join(unrecognized_flags)))

        return valid_flags


class GccToolChain(ToolChain):
    """GCC/Clang/MinGW/Cygwin toolchain (all GCC-family compilers)."""

    def __init__(self, kind='gcc', cc='', cxx='', ld='', ar='',
                 target='', prefix='', tool_prefix=''):
        super().__init__()
        self._kind = kind
        self._target = target or _default_target_for_kind(kind)

        self.cc = cc or _resolve_tool(prefix, tool_prefix, 'gcc')
        self.cxx = cxx or _resolve_tool(prefix, tool_prefix, 'g++')
        self.ld = ld or _resolve_tool(prefix, tool_prefix, 'g++')
        self.ar = ar or _resolve_tool(prefix, tool_prefix, 'ar')
        self.cc_version = self._get_cc_version()
        self._cc_vendor = self._detect_cc_vendor()

        self._tools = {
            'cc': self.cc,
            'cxx': self.cxx,
            'ld': self.ld,
            'ar': self.ar,
            'rc': 'windres' if self._target == 'windows' else None,
            'as': None,
        }

    @property
    def dynamic_lib_suffix(self) -> str:
        if self._target == 'darwin':
            return '.dylib'
        if self._target == 'windows':
            return '.dll'
        return '.so'

    @property
    def lib_prefix(self) -> str:
        return '' if self._target == 'windows' else 'lib'

    @property
    def exe_suffix(self) -> str:
        return '.exe' if self._target == 'windows' else ''

    @property
    def default_linked_libs(self) -> 'tuple[str, ...]':
        """Library aliases the C/C++ driver links implicitly.

        Result is the **union** of:
          * a hardcoded per-platform minimum (libc / libstdc++ / libgcc_s
            etc.), so existing workspaces never regress on baseline coverage
          * what the driver itself reports via ``-###`` parsing, which adds
            things specific to the host's toolchain (e.g. ``c++`` /
            ``c++abi`` on macOS, ``stdc++`` on Linux, vendor-specific
            runtime libs, items introduced by ``-stdlib=libc++`` /
            cross-compiler / wrapper setups)

        Caching is per-instance: ``-###`` is ~100 ms and the answer is
        invariant for the toolchain.

        The hardcoded set takes priority on ordering (predictable for
        link-order-sensitive consumers); auto-detected extras are
        appended.
        """
        cached = getattr(self, '_cached_default_linked_libs', None)
        if cached is not None:
            return cached
        hardcoded = self._hardcoded_default_linked_libs()
        detected = _detect_default_linked_libs(self.cxx)
        # Union, preserving hardcoded order and appending novel extras.
        seen = set(hardcoded)
        extras = tuple(lib for lib in detected if lib not in seen)
        result = hardcoded + extras
        self._cached_default_linked_libs = result
        return result

    def _hardcoded_default_linked_libs(self) -> 'tuple[str, ...]':
        """Last-resort defaults when ``-###`` parsing yields nothing.

        We don't list ``libpthread`` / ``libm`` / ``libdl`` / ``librt``
        for Linux: on glibc those are linked only when explicitly
        requested (``-lpthread`` etc.), which blade already models via
        ``#pthread`` / ``#m`` / ``#dl`` deps. Including them in the
        implicit baseline would hide missing ``#xxx`` deps the check is
        meant to catch.

        For C-only targets the ``stdc++`` / ``c++`` entries contribute
        nothing harmful (they're a no-op for pure C undefined refs).
        """
        if self._target == 'darwin':
            return ('System', 'c++', 'c++abi')
        if self._target == 'windows':
            return ('msvcrt', 'stdc++', 'gcc_s')
        return ('c', 'gcc_s', 'stdc++')


class MsvcToolChain(ToolChain):
    """MSVC toolchain for Windows builds.

    Detects VS installation, MSVC tools, and Windows SDK without relying on
    vcvarsall.bat or pre-set environment variables. Target architecture is
    specified via ``msvc_config.target_arch`` (default: ``'auto'``, which
    matches the host architecture).
    """

    # Map canonical arch names to MSVC directory names and target triplets.
    _ARCH_MAP = {
        'x64':    {'msvc_dir': 'x64',     'triplet': 'x86_64'},
        'x86':    {'msvc_dir': 'x86',     'triplet': 'i386'},
        'arm64':  {'msvc_dir': 'arm64',   'triplet': 'aarch64'},
        'arm64ec':{'msvc_dir': 'arm64ec', 'triplet': 'aarch64'},
    }

    _HOST_ARCH_MAP = {
        'AMD64': 'x64',
        'x86':   'x86',
        'ARM64': 'arm64',
    }

    @property
    def target_arch(self) -> str:
        return self._target_arch

    @property
    def default_linked_libs(self) -> 'tuple[str, ...]':
        """Library aliases MSVC links implicitly into every binary.

        Union of:
          * a hardcoded baseline (UCRT + VC runtime + Win32 base libs), so the
            ``check_undefined`` baseline never regresses even when detection
            fails
          * what the compiler itself reports via ``/DEFAULTLIB`` directives
            (read back with ``dumpbin /directives``), which captures the CRT
            variant actually selected (``/MD`` -> ``msvcrt``, ``/MT`` ->
            ``libcmt``, debug -> ``*d``) plus ``oldnames``

        Per-instance cached: detection compiles a tiny TU (~100 ms) and the
        answer is invariant for the toolchain. Mirrors
        ``GccToolChain.default_linked_libs``; this is the MSVC analog of the
        ``-###`` link-line parse (cl.exe accepts neither ``-###`` nor ``-l``).
        """
        cached = getattr(self, '_cached_default_linked_libs', None)
        if cached is not None:
            return cached
        hardcoded = self._hardcoded_default_linked_libs()
        detected = _detect_default_linked_libs_msvc(
            self.cc, self.get_system_include_paths())
        # Union, preserving hardcoded order and appending novel extras.
        seen = set(hardcoded)
        extras = tuple(lib for lib in detected if lib not in seen)
        result = hardcoded + extras
        self._cached_default_linked_libs = result
        return result

    def _hardcoded_default_linked_libs(self) -> 'tuple[str, ...]':
        """Baseline when ``/DEFAULTLIB`` detection yields nothing.

        MSVC implicitly links the UCRT + VC runtime + Win32 base libs. The
        exact CRT depends on the runtime selection (/MD vs /MT vs the debug
        variants); we list the union so the baseline covers all four
        configurations. lib.exe / link.exe resolves these via the LIB env var
        plus their own search paths.

        The C++ standard library is included via both its import lib
        (``msvcprt``, the /MD variant the compiler selects with
        ``/DEFAULTLIB:msvcprt`` whenever a C++ STL header is used) and the
        static lib (``libcpmt``). Both are needed: ``msvcprt`` exports most
        ``std::`` symbols, but a handful of data globals -- ``std::cerr``, the
        locale facet ``id`` static members -- are referenced by their *plain*
        name (defined inline in the headers) and only ``libcpmt`` carries that
        form (``msvcprt`` has only the ``__imp_`` import stub). Together they
        make the whole C++ stdlib surface ambient, as it is for any C++ binary.
        """
        return ('msvcrt', 'msvcprt', 'libcpmt', 'vcruntime', 'ucrt', 'kernel32')

    def __init__(self, target_arch='auto', msvc_version='auto'):
        super().__init__()
        self._kind = 'msvc'
        self._target = 'windows'
        self.host_arch = self._detect_host_arch()
        self._target_arch = self._resolve_target_arch(target_arch)
        self.msvc_version = msvc_version
        self._msvc_host = 'Host' + self.host_arch
        self._msvc_target = self._ARCH_MAP[self._target_arch]['msvc_dir']

        # Locate installations
        self._vs_path = self._find_vs_path(msvc_version=self.msvc_version)
        self._msvc_path, self._msvc_ver = self._find_msvc_tools()
        self._sdk_path, self._sdk_ver = self._find_windows_sdk()

        # If the requested target arch has no MSVC compiler, try to fall
        # back to an available target (e.g. arm64 host without native arm64
        # MSVC tools can still target x64).
        if self._msvc_path and not self._has_tool_for_target('cl', self._msvc_target):
            fallback = self._find_available_target()
            if fallback:
                console.info(
                    'MSVC has no %s-targeting compiler on this host; '
                    'falling back to target_arch=%s.' % (self._msvc_target, fallback))
                self._msvc_target = fallback
                # Update target_arch to stay consistent
                for k, v in self._ARCH_MAP.items():
                    if v['msvc_dir'] == fallback:
                        self._target_arch = k
                        break

        self._kind = 'msvc'
        self._target = 'windows'

        # Tool commands
        self.cc = self._get_msvc_command('cl')
        self.cxx = self.cc  # MSVC uses same compiler for C and C++
        self.ld = self._get_msvc_command('link')
        self.ar = self._get_msvc_command('lib')
        self.cc_version = self._get_msvc_version()
        self._cc_vendor = 'msvc'

        # Resolve assembler — same directory as cl.exe
        asm_tool = None
        if self._msvc_path:
            for host in (self._msvc_host, 'Hostx64', 'Hostx86'):
                asm_exe = os.path.join(self._msvc_path, 'bin', host,
                                       self._msvc_target,
                                       'ml64.exe' if self._target_arch == 'x64' else 'ml.exe')
                if os.path.exists(asm_exe):
                    asm_tool = asm_exe
                    break

        self._tools = {
            'cc': self.cc,
            'cxx': self.cxx,
            'ld': self.ld,
            'ar': self.ar,
            'rc': self.get_resource_compiler(),
            'as': asm_tool,
        }

    # ------------------------------------------------------------------
    # Architecture resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_host_arch():
        """Detect host machine architecture from environment."""
        machine = os.environ.get('PROCESSOR_ARCHITECTURE', 'AMD64')
        return MsvcToolChain._HOST_ARCH_MAP.get(machine, 'x64')

    def _resolve_target_arch(self, target_arch):
        if target_arch == 'auto':
            return self.host_arch
        if target_arch in self._ARCH_MAP:
            return target_arch
        console.warning('Unknown target_arch "%s", falling back to host (%s)'
                        % (target_arch, self.host_arch))
        return self.host_arch

    def _has_tool_for_target(self, tool, msvc_target):
        """Check whether *tool* exists for the given MSVC target directory."""
        if not self._msvc_path:
            return False
        for host in (self._msvc_host, 'Hostx64', 'Hostx86'):
            tool_path = os.path.join(self._msvc_path, 'bin', host,
                                     msvc_target, f'{tool}.exe')
            if os.path.exists(tool_path):
                return True
        return False

    def _find_available_target(self):
        """Return an MSVC target directory for which tools are available."""
        for target in ('x64', 'x86', 'arm64'):
            if target != self._msvc_target and self._has_tool_for_target('cl', target):
                return target
        return None

    # ------------------------------------------------------------------
    # Installation detection
    # ------------------------------------------------------------------

    @staticmethod
    def _find_vs_path(msvc_version='auto'):
        """Find Visual Studio or BuildTools installation root.

        Args:
            msvc_version: 'auto' for latest, or an MSVC compiler version
                prefix like '14.44' to match a specific toolchain.

        Returns the installation path, or None.
        """
        # 1. VCToolsInstallDir env var (set by VsDevCmd.bat / vcvarsall.bat)
        vctools = os.environ.get('VCToolsInstallDir', '')
        if vctools:
            # VCToolsInstallDir = .../VC/Tools/MSVC/{ver}/bin/HostX64/x64/
            # Walk up 7 levels to the VS root.
            p = os.path.normpath(vctools)
            for _ in range(7):
                p = os.path.dirname(p)
            if os.path.isdir(os.path.join(p, 'VC')):
                return p

        # 2. vswhere.exe
        vs_installer = os.path.join(
            os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
            r'Microsoft Visual Studio\Installer')
        vswhere = os.path.join(vs_installer, 'vswhere.exe')
        if os.path.exists(vswhere):
            return MsvcToolChain._find_vs_with_vswhere(vswhere, msvc_version)

        return None

    @staticmethod
    def _find_vs_with_vswhere(vswhere, msvc_version='auto'):
        """Find a VS installation whose VC toolchain matches *msvc_version*.

        When *msvc_version* is ``'auto'``, the latest installed VS is returned.
        Otherwise, all VS installations are enumerated and the first one whose
        ``VC/Tools/MSVC/`` directory starts with *msvc_version* wins.
        """
        # When 'auto', just pick the latest.
        if msvc_version == 'auto':
            base_args = [
                vswhere, '-latest',
                '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                '-property', 'installationPath',
                '-nologo',
            ]
            for products in [None, 'Microsoft.VisualStudio.Product.BuildTools']:
                args = base_args[:]
                if products:
                    args[1:1] = ['-products', products]
                try:
                    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0 and result.stdout.strip():
                        return result.stdout.strip()
                except Exception:
                    pass
            return None

        # For a specific MSVC version, enumerate all VS installs and check
        # which one provides a matching VC/Tools/MSVC/<version> directory.
        all_args = [
            vswhere, '-all', '-products', '*',
            '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
            '-property', 'installationPath',
            '-nologo',
        ]
        try:
            result = subprocess.run(all_args, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return None
            install_paths = [p.strip() for p in result.stdout.splitlines() if p.strip()]
        except Exception:
            return None

        for vs_path in install_paths:
            msvc_root = os.path.join(vs_path, 'VC', 'Tools', 'MSVC')
            if not os.path.isdir(msvc_root):
                continue
            for ver in sorted(os.listdir(msvc_root), reverse=True):
                if ver.startswith(msvc_version):
                    return vs_path
        return None

    def _find_msvc_tools(self):
        """Find the MSVC tools directory under the VS installation.

        When ``msvc_version`` is set to a specific version (e.g. ``'14.44'``),
        only a matching directory is returned.  When ``'auto'``, the highest
        available version wins.

        Returns (msvc_path, msvc_version) or (None, None).
        """
        if not self._vs_path:
            return None, None
        vc_msvc = os.path.join(self._vs_path, 'VC', 'Tools', 'MSVC')
        if not os.path.isdir(vc_msvc):
            return None, None
        for ver in sorted(os.listdir(vc_msvc), reverse=True):
            if self.msvc_version != 'auto' and not ver.startswith(self.msvc_version):
                continue
            msvc_path = os.path.join(vc_msvc, ver)
            if os.path.isdir(msvc_path):
                return msvc_path, ver
        return None, None

    @staticmethod
    def _find_windows_sdk():
        """Find the Windows SDK installation.

        Returns (sdk_root, sdk_version) or (None, None).
        """
        # 1. Registry (most reliable)
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                r'SOFTWARE\Microsoft\Windows Kits\Installed Roots') as key:
                kits_root = winreg.QueryValueEx(key, 'KitsRoot10')[0]
        except Exception:
            kits_root = os.path.join(
                os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'),
                r'Windows Kits\10')

        if not kits_root or not os.path.isdir(kits_root):
            return None, None

        # 2. Pick the latest installed SDK version
        include_root = os.path.join(kits_root, 'Include')
        if os.path.isdir(include_root):
            for ver in sorted(os.listdir(include_root), reverse=True):
                sdk_inc = os.path.join(include_root, ver)
                if os.path.isdir(sdk_inc):
                    return kits_root, ver

        return kits_root, None

    # ------------------------------------------------------------------
    # Tool path resolution
    # ------------------------------------------------------------------

    def _get_msvc_command(self, tool):
        """Get the path to an MSVC tool executable.

        Detection order:
        1. VCToolsInstallDir env var (already set up by external script)
        2. Discovered MSVC tools path from VS installation
        3. Fallback to PATH via ``where``
        """
        # 1. VCToolsInstallDir
        vctools = os.environ.get('VCToolsInstallDir', '')
        if vctools:
            tool_path = os.path.join(vctools, 'bin', self._msvc_host,
                                     self._msvc_target, f'{tool}.exe')
            if os.path.exists(tool_path):
                return tool_path

        # 2. Discovered MSVC tools path — try preferred host first,
        #    then fallback hosts, all with the resolved target.
        if self._msvc_path:
            for host in (self._msvc_host, 'Hostx64', 'Hostx86'):
                tool_path = os.path.join(self._msvc_path, 'bin', host,
                                         self._msvc_target, f'{tool}.exe')
                if os.path.exists(tool_path):
                    return tool_path

        # 3. Fallback to PATH
        result = subprocess.run(['where', tool], capture_output=True, text=True)
        if result.returncode == 0:
            first_path = result.stdout.strip().split('\n')[0].strip()
            if os.path.isfile(first_path):
                return first_path

        return tool  # Let it fail with a clear error later

    @property
    def dumpbin(self) -> str:
        """Path to ``dumpbin.exe`` -- MSVC's object/library inspector.

        Used by the cc ``check_undefined`` static check as the MSVC analog of
        ``nm``: ``dumpbin /linkermember`` enumerates an import lib's defined
        externals and ``dumpbin /symbols`` separates a static lib's undefined
        from defined externals. Resolved alongside cl / lib / link.
        """
        return self._get_msvc_command('dumpbin')

    def get_resource_compiler(self):
        """Return path to Windows Resource Compiler (``rc.exe``).

        Detection order:
        1. Windows SDK bin directory (discovered from the installation)
        2. Fallback to ``where rc.exe`` on PATH
        """
        if self._sdk_path and self._sdk_ver:
            arch_dir = self._ARCH_MAP[self._target_arch]['msvc_dir']
            tool_path = os.path.join(self._sdk_path, 'Bin', self._sdk_ver,
                                     arch_dir, 'rc.exe')
            if os.path.exists(tool_path):
                return tool_path

        result = subprocess.run(['where', 'rc'], capture_output=True, text=True)
        if result.returncode == 0:
            first_path = result.stdout.strip().split('\n')[0].strip()
            if os.path.isfile(first_path):
                return first_path

        return 'rc'  # Let it fail with a clear error later

    # ------------------------------------------------------------------
    # Compiler metadata
    # ------------------------------------------------------------------

    def _get_msvc_version(self):
        """Get MSVC compiler version string."""
        try:
            result = subprocess.run([self.cc], capture_output=True, text=True)
            output = (result.stdout or '') + '\n' + (result.stderr or '')
            m = re.search(r'Version\s+(\d+\.\d+)', output)
            if m:
                return m.group(1)
        except Exception:
            # cl.exe may not run outside a VS environment; fall back gracefully.
            pass
        return 'unknown'

    def get_cc_commands(self):
        return self.cc, self.cxx, self.ld

    def get_cc_target_arch(self):
        """Return the canonical triplet for the configured target arch."""
        return self._ARCH_MAP[self._target_arch]['triplet']

    def cc_is(self, vendor):
        """Check if compiler matches vendor."""
        return vendor == 'msvc'

    # ------------------------------------------------------------------
    # File naming properties — MSVC conventions
    # ------------------------------------------------------------------

    @property
    def obj_suffix(self) -> str:
        return '.obj'

    @property
    def static_lib_suffix(self) -> str:
        return '.lib'

    @property
    def dynamic_lib_suffix(self) -> str:
        return '.dll'

    @property
    def lib_prefix(self) -> str:
        return ''

    # ------------------------------------------------------------------
    # System include / library paths (so callers don't need vcvarsall)
    # ------------------------------------------------------------------

    def get_system_include_paths(self):
        """Return system include paths (MSVC + Windows SDK headers).

        These are the equivalent of the INCLUDE environment variable set by
        vcvarsall.bat, discovered from the installation.
        """
        paths = []
        if self._msvc_path:
            paths.append(os.path.join(self._msvc_path, 'include'))
        if self._sdk_path and self._sdk_ver:
            sdk_inc = os.path.join(self._sdk_path, 'Include', self._sdk_ver)
            # Same subdirs vcvarsall.bat puts on INCLUDE. 'winrt' provides WRL
            # (wrl.h) used by Direct2D/DirectWrite code; 'cppwinrt' the C++/WinRT
            # projections. Absent subdirs are skipped by the isdir guard.
            for sub in ('ucrt', 'um', 'shared', 'winrt', 'cppwinrt'):
                p = os.path.join(sdk_inc, sub)
                if os.path.isdir(p):
                    paths.append(p)
        return paths

    def get_system_lib_paths(self):
        """Return system library search paths (MSVC + Windows SDK libs).

        These are the equivalent of the LIB environment variable set by
        vcvarsall.bat, discovered from the installation. Paths are
        architecture-specific based on ``target_arch``.
        """
        arch = self._msvc_target
        paths = []
        if self._msvc_path:
            lib = os.path.join(self._msvc_path, 'lib', arch)
            if os.path.isdir(lib):
                paths.append(lib)
        if self._sdk_path and self._sdk_ver:
            sdk_lib = os.path.join(self._sdk_path, 'Lib', self._sdk_ver)
            for sub in ('um', 'ucrt'):
                p = os.path.join(sdk_lib, sub, arch)
                if os.path.isdir(p):
                    paths.append(p)
        return paths

    # ------------------------------------------------------------------
    # Output file naming (MSVC conventions)
    # ------------------------------------------------------------------

    @property
    def exe_suffix(self) -> str:
        return '.exe'

    def object_file_of(self, src):
        """MSVC produces .obj files."""
        return src + '.obj'

    def static_library_name(self, name):
        """MSVC static libraries use .lib extension."""
        return '%s.lib' % name

    def dynamic_library_name(self, name):
        """MSVC dynamic libraries use .dll extension."""
        return '%s.dll' % name

    def import_library_name(self, name):
        """Import library for a DLL: `<name>.dll.lib`.

        Mirrors MinGW's `lib<name>.dll.a` convention so the DLL's import
        library is distinct from a static library (`<name>.lib`). The name
        follows the target (consistent with the static lib); the runtime DLL
        name it points to is recorded inside the import lib by the linker.
        """
        return '%s.dll.lib' % name

    def executable_file_name(self, name):
        """MSVC executables use .exe extension."""
        return name + '.exe'

    @property
    def deps_style(self):
        """MSVC uses 'msvc' deps style in ninja."""
        return 'msvc'

    @property
    def uses_depfile(self):
        """MSVC /showIncludes outputs to stdout, not a depfile."""
        return False

    # ------------------------------------------------------------------
    # Flag filtering
    # ------------------------------------------------------------------

    @staticmethod
    def _map_gcc_flags_to_msvc(flag_list):
        """Map well-known GCC-style flags to MSVC equivalents.

        Only maps flags with clear MSVC counterparts (std, optimize, debug).
        GCC warning flags (-W*), machine flags (-m*), and Linux/glibc macros
        (-D_FILE_OFFSET_BITS, etc.) are intentionally dropped — they have no
        meaning on Windows.
        """
        _STD_MAP = {
            '-std=c90': '/std:c90',
            '-std=c99': '/std:c99',
            '-std=c11': '/std:c11',
            '-std=c17': '/std:c17',
            '-std=c++98': '/std:c++14',
            '-std=c++11': '/std:c++14',
            '-std=c++14': '/std:c++14',
            '-std=c++17': '/std:c++17',
            '-std=c++20': '/std:c++20',
            '-std=c++2a': '/std:c++20',
        }
        _OPT_MAP = {
            '-O0': '/Od',
            '-O1': '/O1',
            '-O2': '/O2',
            '-O3': '/O2',
            '-Os': '/O1',
            '-Og': '/Od',
            '-g': '/Zi',
            '-g0': '/Zi',
            '-g1': '/Zi',
            '-g2': '/Zi',
            '-g3': '/Zi',
        }
        # GCC flags with no MSVC equivalent — silently dropped
        _SKIP_PREFIXES = (
            '-W',           # GCC warning flags
            '-m',           # -m64, -m32, -msse, etc.
            '-f',           # -fno-omit-frame-pointer, -fstack-protector, etc.
        )
        _SKIP_FLAGS = frozenset([
            '-pipe', '-rdynamic', '-gsplit-dwarf',
        ])
        # Linux/glibc feature macros — meaningless on Windows
        _SKIP_DEFINES = frozenset([
            '_FILE_OFFSET_BITS=64',
            '__STDC_CONSTANT_MACROS',
            '__STDC_FORMAT_MACROS',
            '__STDC_LIMIT_MACROS',
        ])

        mapped = []
        for flag in var_to_list(flag_list):
            if flag in _SKIP_FLAGS:
                continue
            if flag in _STD_MAP:
                mapped.append(_STD_MAP[flag])
                continue
            if flag in _OPT_MAP:
                mapped.append(_OPT_MAP[flag])
                continue
            if flag.startswith(_SKIP_PREFIXES):
                continue
            if flag.startswith('-D') and len(flag) > 2:
                name = flag[2:]
                if name in _SKIP_DEFINES:
                    continue
                if ' ' not in name:
                    mapped.append('/D' + name)
                    continue
            if flag.startswith('-I') and len(flag) > 2:
                mapped.append('/I' + flag[2:])
                continue
            mapped.append(flag)
        return mapped

    # Flags that are known-valid MSVC syntax but may fail the stdin compiler
    # test (e.g. /Zi can't write a PDB from stdin, /WX turns padding warnings
    # into errors when the source is piped).  Bypass the test for these.
    _KNOWN_VALID_PREFIXES = (
        '/D',       # Preprocessor defines
        '/I',       # Include paths
        '/Zi', '/ZI', '/Z7',  # Debug info
        '/FS',      # Force synchronous PDB writes
        '/MP',      # Multi-process compilation
        '/std:',    # Language standard
    )

    def filter_cc_flags(self, flag_list, language='c'):
        """Filter MSVC-specific flags by testing each against the compiler."""
        flag_list = var_to_list(flag_list)
        flag_list = self._map_gcc_flags_to_msvc(flag_list)

        # Separate flags into known-valid (bypass test) and need-test.
        trusted, to_test = [], []
        for flag in flag_list:
            if flag.startswith(self._KNOWN_VALID_PREFIXES):
                trusted.append(flag)
            else:
                to_test.append(flag)

        if not to_test:
            return trusted + to_test

        valid_flags, unrecognized_flags = [], []

        # cl.exe cannot read source from stdin (unlike gcc's '-'), so write a
        # throwaway translation unit and compile that. Use the language's own
        # extension so C++-only flags (e.g. /EHsc) are tested in C++ mode.
        ext = '.cpp' if language in ('c++', 'cxx', 'cpp', 'cc') else '.c'
        srcfd, src = tempfile.mkstemp(ext, 'filter_cc_flags_test')
        os.write(srcfd, b'int main() { return 0; }\n')
        os.close(srcfd)

        def _compiles(flags):
            objfd, obj = tempfile.mkstemp('.obj', 'filter_cc_flags_test')
            os.close(objfd)
            try:
                proc = subprocess.Popen(
                    [self.cc, '/nologo', '/c', '/WX', '/Fo' + obj, src] + list(flags),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                proc.communicate()
                return proc.returncode == 0
            finally:
                try:
                    os.remove(obj)
                except OSError:
                    pass

        try:
            if _compiles(to_test):
                return trusted + to_test
            # Something in to_test is bad; re-test each flag individually.
            for flag in to_test:
                (valid_flags if _compiles([flag]) else unrecognized_flags).append(flag)
        finally:
            try:
                os.remove(src)
            except OSError:
                pass

        if unrecognized_flags:
            console.warning('config: Unrecognized {} flags: {}'.format(
                    language, ', '.join(unrecognized_flags)))

        return trusted + valid_flags


# ------------------------------------------------------------------
# Toolchain kind / target helpers
# ------------------------------------------------------------------

# `-l<name>` tokens that appear on a GCC/Clang link command line but
# are NOT library names. ld treats these as flags whose syntax happens
# to start with `-l`. Filter them out of the auto-detected default-
# linked-libs set.
_NON_LIB_DASH_L_FLAGS = frozenset({
    'to_library',   # -lto_library <path>  : selects the LTO plugin (clang on macOS)
})


def _detect_default_linked_libs(cxx: str) -> 'tuple[str, ...]':
    """Auto-detect default-linked libraries by parsing the driver's link command.

    Runs ``<cxx> -### -x c++ /dev/null -o <tmp>`` -- ``-###`` prints the
    full command set the driver would execute without running anything,
    so it's fast and side-effect-free. The link invocation appears as
    a separate line containing the linker executable (``ld``, ``ld64``,
    ``ld.lld``, ``lld``, or ``collect2``); we tokenize it (respecting
    the driver's argument quoting), pull every ``-l<name>``, and filter
    known non-library flags.

    Returns an empty tuple when:
      * the driver doesn't accept ``-###`` (very old / non-standard CC)
      * no link line could be identified
      * the link line has no ``-l<name>`` tokens
    -- caller is expected to fall back to a hardcoded per-platform set.
    """
    import shlex                # noqa: PLC0415  pulled lazily; cold path
    import subprocess           # noqa: PLC0415
    import tempfile             # noqa: PLC0415

    # tempfile path is needed because some drivers refuse to write to
    # /dev/null when the architecture's linker insists on creating a
    # mach-o/ELF header structure.
    with tempfile.NamedTemporaryFile(suffix='.out', delete=False) as f:
        tmp_out = f.name
    try:
        try:
            proc = subprocess.run(
                [cxx, '-###', '-x', 'c++', '/dev/null', '-o', tmp_out],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ()
        # `-###` writes to stderr on both GCC and Clang.
        output = proc.stderr or proc.stdout
    finally:
        try:
            os.unlink(tmp_out)
        except OSError:
            pass  # best-effort cleanup; the temp file may already be gone

    libs: list[str] = []
    seen: set[str] = set()
    # Linker executable markers, ordered roughly by likelihood:
    #  * ``ld``      : Apple ld64 / classic GNU ld
    #  * ``collect2``: GCC's link wrapper that calls the real ld
    #  * ``lld`` /``ld.lld``: LLVM lld
    #  * ``ld64``   : explicit ld64 invocations (some toolchains)
    linker_markers = ('/ld ', '/ld"', '/collect2 ', '/collect2"',
                      '/ld.lld', '/lld ', '/lld"', '/ld64')
    for raw_line in output.splitlines():
        if not any(marker in raw_line for marker in linker_markers):
            continue
        try:
            tokens = shlex.split(raw_line, posix=True)
        except ValueError:
            # Malformed quoting -- skip this line.
            continue
        skip_next = False
        for tok in tokens:
            if skip_next:
                # Argument of a previous flag (e.g. the path that follows
                # ``-lto_library``); not a library entry.
                skip_next = False
                continue
            if tok in _DASH_L_FLAGS_WITH_PATH_ARG:
                skip_next = True
                continue
            entry = _classify_link_token(tok)
            if entry is None or entry in seen:
                continue
            seen.add(entry)
            libs.append(entry)
        if libs:
            # First link line with `-l` tokens wins; subsequent lines
            # would be informational (e.g. echoed copy of the command).
            break
    return tuple(libs)


# Link-line flags that consume a following path argument. The path
# itself must be skipped, otherwise alias-or-direct-path classification
# would mis-pick it as a default-linked library entry.
#
#   -lto_library <plugin.dylib>   : Apple Clang LTO plugin (macOS)
#   -plugin <liblto_plugin.so>    : GCC's LTO plugin loader (Linux)
#   -dynamic-linker <ld.so>       : ELF interpreter (Linux ld; ends in .so.N)
#   -rpath <dir>                  : runtime search path (some flavors take .so)
#   -rpath-link <dir>             : link-time search path
#   -T <linker_script>            : GNU ld linker script
#   -syslibroot <sdk>             : Apple ld64 sysroot
#   -isysroot <sdk>               : compiler driver sysroot
#   -o <output>                   : output file
_DASH_L_FLAGS_WITH_PATH_ARG = frozenset({
    '-lto_library',
    '-plugin',
    '-dynamic-linker',
    '-rpath',
    '-rpath-link',
    '-T',
    '-syslibroot',
    '-isysroot',
    '-o',
})


def _classify_link_token(tok: str) -> 'str | None':
    """Classify a single link-command token and return the entry to add
    to ``default_linked_libs``, or ``None`` to skip.

    Two shapes are interesting:

    * ``-l<alias>`` --- a blade-style library alias. We strip the ``-l``
      and return the alias unchanged. Filter known non-library flags
      (``-lto_library``) and skip the ``-l:literal-filename`` form
      (GNU ld extension we can't represent as a blade alias).
    * Absolute path to a ``.a`` / ``.dylib`` / ``.so`` (or versioned
      ``.so.N``) --- compiler runtime archives like macOS's
      ``libclang_rt.osx.a`` arrive this way; their symbols need to land
      in the baseline too. Return the path verbatim; callers distinguish
      absolute-path entries from aliases by the leading ``/``.

    Everything else (flags, output paths, the user's compiled .o)
    returns ``None``.
    """
    if tok.startswith('-l') and len(tok) > 2:
        # ``-l:libfoo.so.1`` is GNU ld's literal-name form; skip.
        if tok[2] == ':':
            return None
        name = tok[2:]
        if name in _NON_LIB_DASH_L_FLAGS:
            return None
        return name
    # Absolute paths only -- relative paths in the link line are the
    # user's compiled .o (e.g. ``/tmp/cc<hash>.o``); but we want absolute
    # toolchain-installed archives, which always come as full paths.
    if (tok.startswith('/')
            and (tok.endswith('.a') or tok.endswith('.dylib') or '.so' in tok)
            # Exclude the user's compiled .o (cleanups), startup object
            # files, and other non-library outputs from the link line.
            and not tok.endswith('.o')):
        return tok
    return None


def _detect_default_linked_libs_msvc(
        cc: str, include_paths=None) -> 'tuple[str, ...]':
    """Auto-detect MSVC default-linked libraries from compiler directives.

    The MSVC analog of ``-###`` link-line parsing: the CRT and STL headers (and
    the compiler itself) inject ``#pragma comment(lib, ...)`` directives into
    every object file, naming the runtime libraries link.exe pulls implicitly --
    the CRT variant the runtime flag selected (``/MD`` -> ``MSVCRT``, ``/MT`` ->
    ``LIBCMT``, debug -> ``*D``), the matching C++ standard library
    (``MSVCPRT`` / ``LIBCPMT``), and ``OLDNAMES``. We compile a small
    translation unit and read those ``/DEFAULTLIB`` directives back with
    ``dumpbin /directives``.

    ``cc`` is the path to ``cl.exe``; ``dumpbin.exe`` is expected alongside it,
    falling back to PATH. ``include_paths`` (the toolchain's system include
    dirs) is needed because the probe ``#include``s a C++ STL header so the
    compiler injects the C++ standard library's ``/DEFAULTLIB`` -- that lib
    (``msvcprt``) defines ``std::`` symbols (``_Xlength_error``, the locale
    facets, iostream globals) that a bare ``int main(){}`` never references. We
    compile with ``/MD`` to match blade's default MSVC runtime (``cc.cppflags``
    in the builtin config); since the result is unioned with the hardcoded
    baseline, the exact variant is not critical.

    Returns an empty tuple on any failure (cl/dumpbin missing, compile error,
    no directives) -- the caller falls back to the hardcoded baseline, so there
    is no regression risk.
    """
    import shutil               # noqa: PLC0415  pulled lazily; cold path
    import subprocess           # noqa: PLC0415
    import tempfile             # noqa: PLC0415

    dumpbin = os.path.join(os.path.dirname(cc), 'dumpbin.exe')
    if not os.path.isfile(dumpbin):
        found = shutil.which('dumpbin')
        if not found:
            return ()
        dumpbin = found

    # INCLUDE lets the probe pull STL headers (for the C++ stdlib DEFAULTLIB).
    env = os.environ.copy()
    if include_paths:
        env['INCLUDE'] = os.pathsep.join(include_paths)

    tmpdir = tempfile.mkdtemp(prefix='blade_msvc_libs_')
    try:
        src = os.path.join(tmpdir, 'probe.cpp')
        obj = os.path.join(tmpdir, 'probe.obj')
        with open(src, 'w') as f:
            # <string> pulls the throw helpers, <iostream> the locale/stream
            # globals -- together they trigger /DEFAULTLIB:msvcprt.
            f.write('#include <string>\n#include <iostream>\n'
                    'int main() { std::string s; std::cout << s; '
                    'return (int)s.size(); }\n')
        try:
            proc = subprocess.run(
                [cc, '/nologo', '/c', '/MD', src, '/Fo' + obj],
                capture_output=True, text=True, timeout=30, check=False,
                cwd=tmpdir, env=env)
        except (OSError, subprocess.TimeoutExpired):
            return ()
        if proc.returncode != 0 or not os.path.isfile(obj):
            return ()
        try:
            dump = subprocess.run(
                [dumpbin, '/nologo', '/directives', obj],
                capture_output=True, text=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return ()
        output = dump.stdout or ''
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    libs: list[str] = []
    seen: set[str] = set()
    for raw_line in output.splitlines():
        entry = _classify_msvc_directive(raw_line)
        if entry is None or entry in seen:
            continue
        seen.add(entry)
        libs.append(entry)
    return tuple(libs)


def _classify_msvc_directive(line: str) -> 'str | None':
    """Extract the library alias from a ``dumpbin /directives`` line.

    Lines of interest carry a linker directive ``/DEFAULTLIB:MSVCRT`` or
    ``/DEFAULTLIB:"libname.lib"`` (drivers vary on quoting and on the ``.lib``
    suffix). Returns the normalized blade alias (lowercased, quotes and the
    ``.lib`` suffix stripped) or ``None`` for any other line (the ``Linker
    Directives`` banner, ``/FAILIFMISMATCH``, ``/merge``, blanks, ...).
    """
    text = line.strip()
    marker = '/DEFAULTLIB:'
    idx = text.upper().find(marker)
    if idx == -1:
        return None
    value = text[idx + len(marker):].strip()
    parts = value.split()
    value = parts[0] if parts else ''
    value = value.strip('"').strip()
    if not value:
        return None
    if value.lower().endswith('.lib'):
        value = value[:-4]
    return value.lower() or None


_CC_TOOLCHAIN_KINDS = {'gcc', 'clang', 'msvc', 'mingw', 'cygwin'}

_HOST_TARGET_MAP = {
    'linux': 'linux',
    'linux2': 'linux',
    'darwin': 'darwin',
    'win32': 'windows',
    'cygwin': 'windows',
    'msys': 'windows',
}


def _default_target_for_kind(kind):
    """Default ``target`` for a given toolchain *kind*."""
    if kind in ('mingw', 'cygwin', 'msvc'):
        return 'windows'
    return _HOST_TARGET_MAP.get(sys.platform, 'linux')


def _resolve_tool(prefix, tool_prefix, tool_name):
    """Resolve a tool path from *prefix* + *tool_prefix* + *tool_name*.

    When *prefix* is set, only ``<prefix>/bin/<tool_prefix><tool_name>`` and
    ``<prefix>/<tool_prefix><tool_name>`` are checked; PATH is never searched.
    When *prefix* is empty, ``which()`` on PATH is used instead.

    Returns the best-effort path string (may be a bare name if nothing found).
    """
    import shutil
    full_name = tool_prefix + tool_name
    if prefix:
        for subdir in ('bin', ''):
            path = os.path.join(prefix, subdir, full_name) if subdir else os.path.join(prefix, full_name)
            if os.path.isfile(path):
                return path
        return full_name
    found = shutil.which(full_name)
    if found:
        return found
    return full_name


def _auto_detect_kind():
    """Auto-detect toolchain kind from the host platform."""
    if os.name == 'nt':
        return 'msvc'
    import shutil
    if shutil.which('gcc'):
        return 'gcc'
    if shutil.which('clang'):
        return 'clang'
    return 'gcc'  # fallback


def _lookup_config(tc_section, cc_toolchain):
    """Look up a toolchain config by *name* or *kind*.

    Returns ``(config_dict | None, kind_str | '')``.
    """
    # 1. Match by name (named config stored directly in the section)
    if cc_toolchain:
        named = tc_section.get(cc_toolchain)
        if isinstance(named, dict):
            return named, named.get('kind', '')
        # 2. Match by kind directly
        if cc_toolchain in _CC_TOOLCHAIN_KINDS:
            return None, cc_toolchain
        console.warning(
            'Unknown toolchain "%s", falling back to default or auto-detection'
            % cc_toolchain)
    return None, ''


def _resolve_config(cfg, tc_section):
    """Given an optional named *cfg* dict, return (kind, target, prefix,
    tool_prefix, cc, cxx, ld, ar, target_arch, msvc_version).

    Falls back to the unnamed default entry (key ``''``) when *cfg* is None.
    """
    if cfg is None:
        cfg = tc_section.get('', {})
    kind = cfg.get('kind', '') or _auto_detect_kind()
    target = cfg.get('target', '') or _default_target_for_kind(kind)
    prefix = cfg.get('prefix', '')
    tool_prefix = cfg.get('tool_prefix', '')
    cc = cfg.get('cc', '')
    cxx = cfg.get('cxx', '')
    ld = cfg.get('ld', '')
    ar = cfg.get('ar', '')
    target_arch = cfg.get('target_arch', '')
    msvc_version = cfg.get('msvc_version', '')
    return kind, target, prefix, tool_prefix, cc, cxx, ld, ar, target_arch, msvc_version


def create_toolchain(cc_toolchain=''):
    """Create the toolchain based on config, CLI flag, or auto-detection.

    Selection priority:
    1. ``--cc-toolchain=`` CLI flag (match by *name* then *kind*)
    2. ``cc_config.toolchain`` in BLADE_ROOT (default toolchain name)
    3. ``cc_toolchain_config()`` in BLADE_ROOT (named or unnamed)
    4. Auto-detection from host platform

    Args:
        cc_toolchain: Value of ``--cc-toolchain`` CLI flag (``''`` if not set).
    """
    from blade import config as blade_config
    tc_section = blade_config.get_section('cc_toolchain_config')

    if not cc_toolchain:
        cc_toolchain = blade_config.get_section('cc_config').get('toolchain', '')

    cfg, kind = _lookup_config(tc_section, cc_toolchain)

    (kind, target, prefix, tool_prefix, cc, cxx, ld, ar,
     target_arch, msvc_version) = _resolve_config(cfg, tc_section)

    # Override kind from CLI if it was a kind match rather than named config
    if cfg is None and cc_toolchain in _CC_TOOLCHAIN_KINDS:
        kind = cc_toolchain

    if kind == 'msvc':
        msvc_config = blade_config.get_section('msvc_config')
        target_arch = (target_arch or
                       msvc_config.get('target_arch', 'auto'))
        msvc_version = (msvc_version or
                        msvc_config.get('msvc_version', 'auto'))
        return MsvcToolChain(target_arch=target_arch, msvc_version=msvc_version)

    return GccToolChain(
        kind=kind,
        cc=cc, cxx=cxx, ld=ld, ar=ar,
        target=target,
        prefix=prefix,
        tool_prefix=tool_prefix,
    )
