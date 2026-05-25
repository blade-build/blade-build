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

    # ------------------------------------------------------------------
    # Target file labels — internal keys used by cc_targets to register
    # and look up output files.  These are conventional and do not need
    # to match file extensions (e.g. MSVC keeps 'so' even though the
    # file ends in .dll).
    # ------------------------------------------------------------------
    STATIC_LIB_LABEL = 'a'
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
    def all_dynamic_lib_suffixes(self) -> tuple[str, ...]:
        """All dynamic-library suffixes across supported platforms.

        Used for diagnostic checks (e.g. detecting ambiguous cc_plugin names).
        """
        return ('.so', '.dylib', '.dll')

    def __init__(self):
        pass

    @staticmethod
    def _get_cc_command(env, default):
        """Get a cc command.
        """
        return os.path.join(os.environ.get('TOOLCHAIN_DIR', ''), os.environ.get(env, default))  # pyright: ignore[reportCallIssue, reportArgumentType]

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

    @staticmethod
    def get_cc_target_arch():
        """Get the cc target architecture."""
        cc = ToolChain._get_cc_command('CC', 'gcc')
        returncode, stdout, stderr = run_command([cc, '-dumpmachine'])
        if returncode == 0:
            return stdout.strip()
        return ''

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
        return name

    @property
    def deps_style(self):
        """Return the ninja deps style: 'gcc' or 'msvc'."""
        return 'gcc'

    @property
    def uses_depfile(self):
        """Whether the compiler generates a .d depfile."""
        return True

    def supports_resource_compilation(self):
        """Whether the toolchain can compile Windows .rc resource files."""
        return False

    def get_resource_compiler(self):
        """Return path to the Windows Resource Compiler (``rc.exe``).

        Only meaningful when ``supports_resource_compilation()`` returns
        ``True``; callers must guard accordingly."""
        return 'rc'  # let it fail if called unsafely

    def get_system_include_paths(self):
        """Return system include paths, or empty list if not applicable."""
        return []

    def get_system_lib_paths(self):
        """Return system library search paths, or empty list if not applicable."""
        return []

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
    """GCC/Clang toolchain for Linux and macOS builds."""

    def __init__(self):
        super().__init__()
        self.cc = self._get_cc_command('CC', 'gcc')
        self.cxx = self._get_cc_command('CXX', 'g++')
        self.ld = self._get_cc_command('LD', 'g++')
        self.cc_version = self._get_cc_version()
        self.ar = self._get_cc_command('AR', 'ar')
        self._cc_vendor = self._detect_cc_vendor()

    @property
    def dynamic_lib_suffix(self) -> str:
        return '.dylib' if sys.platform == 'darwin' else '.so'


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

    def __init__(self, target_arch='auto', msvc_version='auto'):
        super().__init__()
        self.host_arch = self._detect_host_arch()
        self.target_arch = self._resolve_target_arch(target_arch)
        self.msvc_version = msvc_version
        self._msvc_host = 'Host' + self.host_arch
        self._msvc_target = self._ARCH_MAP[self.target_arch]['msvc_dir']

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
                console.warning(
                    'MSVC has no %s-targeting compiler on this host; '
                    'falling back to target_arch=%s. '
                    'Set msvc_config.target_arch explicitly to suppress '
                    'this warning.' % (self._msvc_target, fallback))
                self._msvc_target = fallback
                # Update target_arch to stay consistent
                for k, v in self._ARCH_MAP.items():
                    if v['msvc_dir'] == fallback:
                        self.target_arch = k
                        break

        # Tool commands
        self.cc = self._get_msvc_command('cl')
        self.cxx = self.cc  # MSVC uses same compiler for C and C++
        self.ld = self._get_msvc_command('link')
        self.ar = self._get_msvc_command('lib')
        self.cc_version = self._get_msvc_version()
        self._cc_vendor = 'msvc'

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

    def get_resource_compiler(self):
        """Return path to Windows Resource Compiler (``rc.exe``).

        Detection order:
        1. Windows SDK bin directory (discovered from the installation)
        2. Fallback to ``where rc.exe`` on PATH
        """
        if self._sdk_path and self._sdk_ver:
            arch_dir = self._ARCH_MAP[self.target_arch]['msvc_dir']
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
        return self._ARCH_MAP[self.target_arch]['triplet']

    def cc_is(self, vendor):
        """Check if compiler matches vendor."""
        return vendor == 'msvc'

    def supports_resource_compilation(self):
        return True

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
            for sub in ('ucrt', 'um', 'shared'):
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

    def object_file_of(self, src):
        """MSVC produces .obj files."""
        return src + '.obj'

    def static_library_name(self, name):
        """MSVC static libraries use .lib extension."""
        return '%s.lib' % name

    def dynamic_library_name(self, name):
        """MSVC dynamic libraries use .dll extension."""
        return '%s.dll' % name

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

        fd, obj = tempfile.mkstemp('.obj', 'filter_cc_flags_test')
        try:
            argv = [self.cc, '/nologo', '/c', '/Fo' + obj, '/WX', '/Tc-'] + to_test
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            _, _ = proc.communicate(input=b'int main() { return 0; }\n')
            returncode = proc.returncode
        finally:
            try:
                os.remove(obj)
            except OSError:
                # Temp file may already be deleted by the compiler on error.
                pass
            os.close(fd)

        if returncode == 0:
            return trusted + to_test
        # When a flag is unrecognized, MSVC puts it in the error output.
        # Re-test each flag individually to identify bad ones.
        for flag in to_test:
            fd2, obj2 = tempfile.mkstemp('.obj', 'filter_cc_flags_test')
            try:
                test_argv = [self.cc, '/nologo', '/c', '/Fo' + obj2, '/WX', '/Tc-', flag]
                proc = subprocess.Popen(
                    test_argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE)
                _, _ = proc.communicate(input=b'int main() { return 0; }\n')
                if proc.returncode == 0:
                    valid_flags.append(flag)
                else:
                    unrecognized_flags.append(flag)
            finally:
                try:
                    os.remove(obj2)
                except OSError:
                    # Temp file may not exist or be already cleaned up.
                    pass
                os.close(fd2)

        if unrecognized_flags:
            console.warning('config: Unrecognized {} flags: {}'.format(
                    language, ', '.join(unrecognized_flags)))

        return valid_flags


def create_toolchain(m=None):
    """Create the appropriate toolchain for the current platform.

    On Windows, reads ``msvc_config.target_arch`` to determine the target
    architecture. The *m* parameter (bits, ``'32'`` or ``'64'``) is reserved
    for future cross-compilation support.

    Returns:
        A ToolChain instance appropriate for the current OS.
    """
    if os.name == 'nt':
        from blade import config as blade_config
        msvc_config = blade_config.get_section('msvc_config')
        target_arch = msvc_config.get('target_arch', 'auto')
        msvc_version = msvc_config.get('msvc_version', 'auto')
        return MsvcToolChain(target_arch=target_arch, msvc_version=msvc_version)
    return GccToolChain()
