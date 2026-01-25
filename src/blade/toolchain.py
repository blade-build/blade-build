# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Chong Peng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
This module deals with the build toolchains.
"""

from __future__ import absolute_import
from __future__ import print_function

import os
import re
import tempfile

from blade import console
from blade.util import var_to_list, iteritems, run_command

# example: Cuda compilation tools, release 11.0, V11.0.194
_nvcc_version_re = re.compile(r'V(\d+\.\d+\.\d+)')

class BuildArchitecture(object):
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
        for k, v in iteritems(BuildArchitecture._build_architecture):
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


class ToolChain(object):
    """The build platform handles and gets the platform information."""

    def __init__(self):
        if os.name == 'nt':  # Windows
            self.__class__ = WindowsToolChain
            WindowsToolChain.__init__(self)
        else:
            self.cc = self._get_cc_command('CC', 'gcc')
            self.cxx = self._get_cc_command('CXX', 'g++')
            self.ld = self._get_cc_command('LD', 'g++')
            self.cc_version = self._get_cc_version()
            self.ar = self._get_cc_command('AR', 'ar')

    @staticmethod
    def _get_cc_command(env, default):
        """Get a cc command.
        """
        return os.path.join(os.environ.get('TOOLCHAIN_DIR', ''), os.environ.get(env, default))

    def _get_cc_version(self):
        version = ''
        returncode, stdout, stderr = run_command(self.cc + ' -dumpversion', shell=True)
        if returncode == 0:
            version = stdout.strip()
        if not version:
            console.fatal('Failed to obtain cc toolchain.')
        return version

    @staticmethod
    def get_cc_target_arch():
        """Get the cc target architecture."""
        cc = ToolChain._get_cc_command('CC', 'gcc')
        returncode, stdout, stderr = run_command(cc + ' -dumpmachine', shell=True)
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
        """Is cc is used for C/C++ compilation match vendor."""
        return vendor in self.cc

    def filter_cc_flags(self, flag_list, language='c'):
        """Filter out the unrecognized compilation flags."""
        flag_list = var_to_list(flag_list)
        valid_flags, unrecognized_flags = [], []

        # Put compilation output into test.o instead of /dev/null
        # because the command line with '--coverage' below exit
        # with status 1 which makes '--coverage' unsupported
        # echo "int main() { return 0; }" | gcc -o /dev/null -c -x c --coverage - > /dev/null 2>&1
        fd, obj = tempfile.mkstemp('.o', 'filter_cc_flags_test')
        cmd = ('export LC_ALL=C; echo "int main() { return 0; }" | '
               '%s -o %s -c -x %s -Werror %s -' % (
                   self.cc, obj, language, ' '.join(flag_list)))
        returncode, _, stderr = run_command(cmd, shell=True)

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
            console.warning('config: Unrecognized %s flags: %s' % (
                    language, ', '.join(unrecognized_flags)))

        return valid_flags


class WindowsToolChain(ToolChain):
    """Windows toolchain using MSVC compiler."""
    
    def __init__(self):
        super(WindowsToolChain, self).__init__()
        self.cc = self._get_msvc_command('cl')
        self.cxx = self.cc  # MSVC uses same compiler for C/C++
        self.ld = self._get_msvc_command('link')
        self.ar = self._get_msvc_command('lib')
        self.cc_version = self._get_msvc_version()
        self._setup_msvc_environment()
    
    def _get_msvc_command(self, tool):
        """Get MSVC tool command path."""
        # Check Visual Studio installation paths
        vs_paths = [
            os.environ.get('VCINSTALLDIR', ''),
            r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC',
            r'C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\VC\Tools\MSVC',
        ]
        
        for vs_path in vs_paths:
            if vs_path and os.path.exists(vs_path):
                tool_path = os.path.join(vs_path, 'bin', 'Hostx64', 'x64', f'{tool}.exe')
                if os.path.exists(tool_path):
                    return tool_path
        
        # Fallback to PATH
        return tool
    
    def _get_msvc_version(self):
        """Get MSVC compiler version."""
        try:
            returncode, stdout, stderr = run_command(self.cc + ' 2>&1', shell=True)
            if returncode == 0 and stdout:
                # Parse version from output like "Microsoft (R) C/C++ Optimizing Compiler Version 19.35.32215.1"
                for line in stdout.split('\n'):
                    if 'Version' in line:
                        version_match = re.search(r'Version\s+(\d+\.\d+)', line)
                        if version_match:
                            return version_match.group(1)
        except Exception:
            pass
        return 'unknown'
    
    def _setup_msvc_environment(self):
        """Setup MSVC environment variables."""
        # These should be set by vcvarsall.bat in practice
        if not os.environ.get('INCLUDE'):
            os.environ['INCLUDE'] = ''
        if not os.environ.get('LIB'):
            os.environ['LIB'] = ''
    
    def get_cc_commands(self):
        return self.cc, self.cxx, self.ld
    
    def cc_is(self, vendor):
        """Check if compiler matches vendor."""
        if vendor == 'msvc':
            return True
        return vendor.lower() in self.cc.lower()
    
    def filter_cc_flags(self, flag_list, language='c'):
        """Filter MSVC-specific flags."""
        flag_list = var_to_list(flag_list)
        valid_flags = []
        unrecognized_flags = []
        
        # MSVC-specific flag mapping
        gcc_to_msvc = {
            '-Wall': '/W3',
            '-Wextra': '/W4',
            '-O2': '/O2',
            '-O0': '/Od',
            '-g': '/Zi',
            '-fPIC': '',  # Not needed on Windows
            '-shared': '/DLL',
            '-c': '/c',
            '-o': '/Fo',
            '-D': '/D',
            '-I': '/I',
        }
        
        for flag in flag_list:
            if flag.startswith('-'):
                # Try to map GCC flag to MSVC
                msvc_flag = gcc_to_msvc.get(flag)
                if msvc_flag:
                    if msvc_flag:  # Skip empty mappings
                        valid_flags.append(msvc_flag)
                elif flag in ['-fno-omit-frame-pointer', '-D_FILE_OFFSET_BITS=64']:
                    # Skip Unix-specific flags
                    continue
                else:
                    unrecognized_flags.append(flag)
            else:
                valid_flags.append(flag)
        
        if unrecognized_flags:
            console.warning('config: Unrecognized MSVC flags: %s' % 
                          ', '.join(unrecognized_flags))
        
        return valid_flags
