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
    """The build platform handles and gets the platform information."""

    def __init__(self):
        self.cc = self._get_cc_command('CC', 'gcc')
        self.cxx = self._get_cc_command('CXX', 'g++')
        self.ld = self._get_cc_command('LD', 'g++')
        self.cc_version = self._get_cc_version()
        self.ar = self._get_cc_command('AR', 'ar')
        self._cc_vendor = self._detect_cc_vendor()

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
        return src + '.o'

    def static_library_name(self, name):
        """Return the static library output name for a given target name."""
        return 'lib%s.a' % name

    def dynamic_library_name(self, name):
        """Return the dynamic library output name for a given target name."""
        return 'lib%s.so' % name

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


class MsvcToolChain(ToolChain):
    """MSVC toolchain for Windows builds."""

    def __init__(self):
        self.cc = self._get_msvc_command('cl')
        self.cxx = self.cc  # MSVC uses same compiler for C and C++
        self.ld = self._get_msvc_command('link')
        self.ar = self._get_msvc_command('lib')
        self.cc_version = self._get_msvc_version()
        self._cc_vendor = 'msvc'

    @staticmethod
    def _get_msvc_command(tool):
        """Get MSVC tool command path using vswhere."""
        vswhere = os.path.join(os.environ.get('ProgramFiles(x86)',
                               r'C:\Program Files (x86)'),
                               r'Microsoft Visual Studio\Installer\vswhere.exe')
        if os.path.exists(vswhere):
            try:
                result = subprocess.run(
                    [vswhere, '-latest', '-products', '*',
                     '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64',
                     '-property', 'installationPath'],
                    capture_output=True, text=True, timeout=30)
                if result.returncode == 0 and result.stdout.strip():
                    vs_path = result.stdout.strip()
                    vc_path = os.path.join(vs_path, 'VC', 'Tools', 'MSVC')
                    if os.path.exists(vc_path):
                        # Find the latest MSVC version directory
                        versions = sorted(os.listdir(vc_path), reverse=True)
                        for ver in versions:
                            tool_path = os.path.join(vc_path, ver, 'bin', 'Hostx64', 'x64',
                                                     f'{tool}.exe')
                            if os.path.exists(tool_path):
                                return tool_path
            except Exception:
                pass

        # Fallback: check if tool is in PATH
        result = subprocess.run(['where', tool], capture_output=True, text=True)
        if result.returncode == 0:
            return tool

        return tool  # Let it fail with a clear error later

    def _get_msvc_version(self):
        """Get MSVC compiler version string."""
        try:
            result = subprocess.run([self.cc], capture_output=True, text=True)
            output = (result.stdout or '') + '\n' + (result.stderr or '')
            m = re.search(r'Version\s+(\d+\.\d+)', output)
            if m:
                return m.group(1)
        except Exception:
            pass
        return 'unknown'

    def get_cc_commands(self):
        return self.cc, self.cxx, self.ld

    def get_cc_target_arch(self):
        """Get the MSVC target architecture."""
        if 'x64' in (self.cc or '').lower() or os.environ.get('VSCMD_ARG_TGT_ARCH') == 'x64':
            return 'x86_64'
        return 'i386'

    def cc_is(self, vendor):
        """Check if compiler matches vendor."""
        return vendor == 'msvc'

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

    def filter_cc_flags(self, flag_list, language='c'):
        """Filter MSVC-specific flags by testing each against the compiler."""
        flag_list = var_to_list(flag_list)
        valid_flags, unrecognized_flags = [], []

        fd, obj = tempfile.mkstemp('.obj', 'filter_cc_flags_test')
        try:
            argv = [self.cc, '/nologo', '/c', '/Fo' + obj, '/WX', '/Tc-'] + list(flag_list)
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
                pass
            os.close(fd)

        if returncode == 0:
            return flag_list
        # When a flag is unrecognized, MSVC puts it in the error output.
        # Re-test each flag individually to identify bad ones.
        for flag in flag_list:
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
                    pass
                os.close(fd2)

        if unrecognized_flags:
            console.warning('config: Unrecognized {} flags: {}'.format(
                    language, ', '.join(unrecognized_flags)))

        return valid_flags


def create_toolchain(m=None):
    """Create the appropriate toolchain for the current platform.

    Args:
        m: Optional architecture bits string ('32' or '64'), passed through for
           potential future use.
    Returns:
        A ToolChain instance appropriate for the current OS.
    """
    if os.name == 'nt':
        return MsvcToolChain()
    return ToolChain()
