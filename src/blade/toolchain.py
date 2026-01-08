# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Chong Peng <michaelpeng@tencent.com>
# Date:   October 20, 2011
# coding: utf-8


"""
This module deals with the build toolchains.
"""

from __future__ import absolute_import
from __future__ import print_function

import os
import subprocess
import re
import tempfile

from blade import config
from blade import console
from blade.util import var_to_list, iteritems, override, run_command

# example: Cuda compilation tools, release 11.0, V11.0.194
_nvcc_version_re = re.compile(r'V(\d+\.\d+\.\d+)')


def _shell_support_pipefail():
    """Whether current shell support the `pipefail` option."""
    return subprocess.call('set -o pipefail 2>/dev/null', shell=True) == 0


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
            'alias': ['amd64', 'x64'],
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


class CcToolChain(object):
    """The build platform handles and gets the platform information."""

    def __init__(self):
        self.cc = ''
        self.cxx = ''
        self.ld = ''
        self.cc_version = ''
        self.ar = ''

    @staticmethod
    def get_cc_target_arch():
        """Get the cc target architecture."""
        cc = CcToolChain._get_cc_command('CC', 'gcc')
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

    def is_kind_of(self, vendor):
        """Is cc is used for C/C++ compilation match vendor."""
        raise NotImplementedError

    def target_arch(self):
        """Return architecture of target machine."""
        raise NotImplementedError

    def target_bits(self):
        """Return number of bits of target machine."""
        raise NotImplementedError

    def filter_cc_flags(self, flag_list, language='c'):
        """Filter out the unrecognized compilation flags."""
        raise NotImplementedError

    def object_file_of(self, source_file):
        """
        Get the object file name from the source file.
        """
        raise NotImplementedError

    def static_library_name(self, name):
        """
        Get the static library file name from the name.
        """
        raise NotImplementedError

    def dynamic_library_name(self, name):
        """
        Get the library file name from the name.
        """
        raise NotImplementedError

    def executable_file_name(self, name):
        """
        Get the executable file name from the name.
        """
        raise NotImplementedError
    
    def get_compile_commands(self, build_dir, cppflags, is_dump):
        """
        Get the compile commands for the specified source file.
        """
        raise NotImplementedError
    
    def get_link_command(self):
        """
        Get the link command.
        """
        raise NotImplementedError
    
    def get_shared_link_command(self):
        """
        Get the link command for dynamic library.
        """
        raise NotImplementedError
    
    def get_static_library_command(self):
        """
        Get the static library command.
        """
        raise NotImplementedError

# To verify whether a header file is included without depends on the library it belongs to,
# we use the gcc's `-H` option to generate the inclusion stack information, see
# https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html for details.
# But this information is output to stderr mixed with diagnostic messages.
# So we use this awk script to split them.
#
# The inclusion information is writes to stdout, other normal diagnostic message is write to stderr.
#
# NOTE the `$$` is required by ninja. and the `Multiple...` followed by multi lines of filepath are useless part.
# `多个防止重包含可能对其有用：` is the same as `Multiple...` in Chinese.
# After `Multiple...`, maybe there are still some useful messages, such as cuda error.
_INCLUSION_STACK_SPLITTER = (r"awk '"
    r"""/Multiple include guards may be useful for:|多个防止重包含可能对其有用：/ {stop=1} """  # Can't exit here otherwise SIGPIPE maybe occurs.
    r"""/^\.+ [^\/]/ && !end { started=1 ; print $$0} """  # Non absolute path, neither header list after error message.
    r"""!/^\.+ / && started {end=1} """  # mark the error message when polling header list
    r"""!/^\.+ / && (!stop || (!/Multiple include guards may be useful for:|多个防止重包含可能对其有用：/ && !/^[a-zA-Z0-9\.\/\+_-]+$$/ )) {print $$0 > "/dev/stderr"}"""  # Maybe error messages
    r"'"
)


class CcToolChainGcc(CcToolChain):
    """The build platform handles and gets the platform information."""

    def __init__(self):
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
        cc = CcToolChain._get_cc_command('CC', 'gcc')
        returncode, stdout, stderr = run_command(cc + ' -dumpmachine', shell=True)
        if returncode == 0:
            return stdout.strip()
        return ''

    @override
    def is_kind_of(self, vendor):
        return vendor in ('gcc', 'clang', 'gcc')

    @override
    def object_file_of(self, source_file):
        return source_file + '.o'

    @override
    def executable_file_name(self, name):
        if os.name == 'nt':
            return name + '.exe'
        return name

    def _cc_compile_command_wrapper_template(self, inclusion_stack_file, cuda=False):
        """Calculate the cc compile command wrapper template."""
        print_header_option = '-H'
        if cuda:
            print_header_option = '-Xcompiler -H'

        if _shell_support_pipefail():
            # Use `pipefail` to ensure that the exit code is correct.
            template = 'export LC_ALL=C; set -o pipefail; %%s %s 2>&1 | %s > %s' % (
                print_header_option, _INCLUSION_STACK_SPLITTER, inclusion_stack_file)
        else:
            # Some shell such as Ubuntu's `dash` doesn't support pipefail, make a workaround.
            template = ('export LC_ALL=C; %%s %s 2> ${out}.err; ec=$$?; %s < ${out}.err > %s ; '
                        'rm -f ${out}.err; exit $$ec') % (
                            print_header_option, _INCLUSION_STACK_SPLITTER, inclusion_stack_file)

        return template

    @override
    def get_compile_commands(self, build_dir, cppflags, is_dump):
        cc_config = config.get_section('cc_config')
        cflags, cxxflags = cc_config['cflags'], cc_config['cxxflags']
        cppflags = cc_config['cppflags'] + cppflags
        includes = cc_config['extra_incs']
        includes = includes + ['.', build_dir]
        includes = ' '.join(['-I%s' % inc for inc in includes])

        cc_command = ('%s -o ${out} -MMD -MF ${out}.d -c -fPIC %s %s ${optimize} '
                      '${c_warnings} ${cppflags} %s ${includes} ${in}') % (
                              self.cc, ' '.join(cflags), ' '.join(cppflags), includes)
        cxx_command = ('%s -o ${out} -MMD -MF ${out}.d -c -fPIC %s %s ${optimize} '
                       '${cxx_warnings} ${cppflags} %s ${includes} ${in}') % (
                               self.cxx, ' '.join(cxxflags), ' '.join(cppflags), includes)
        securecc_command = (cc_config['secretcc'] + ' ' + cxx_command)

        hdrs_command = self._hdrs_command(cxxflags, cppflags, includes)

        if is_dump:
            # When dumping compdb, a raw compile command without wrapper should be generated,
            # otherwise some tools can't handle it.
            return cc_command, cxx_command, securecc_command, hdrs_command
        template = self._cc_compile_command_wrapper_template('${out}.H')
        return template % cc_command, template % cxx_command, template % securecc_command, hdrs_command

    def _hdrs_command(self, flags, cppflags, includes):
        """
        Command to generate cc inclusion information file for header file to check dependency missing.
        See the '-H' in https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html for details.
        """
        args = (' -o /dev/null -E -MMD -MF ${out}.d %s %s -w ${cppflags} %s ${includes} ${in} '
                '2> ${out}.err' % (' '.join(flags), ' '.join(cppflags), includes))

        # The `-fdirectives-only` option can significantly increase the speed of preprocessing,
        # but errors may occur under certain boundary conditions (for example,
        # `#if __COUNTER__ == __COUNTER__ + 1`),
        # try the command again without it on error.
        cmd1 = self.cc + ' -fdirectives-only' + args
        cmd2 = self.cc + args

        # If the first cpp command fails, the second cpp command will be executed.
        # The error message of the first command should be completely ignored.
        return ('export LC_ALL=C; %s || %s; ec=$$?; %s ${out}.err > ${out}; '
                'rm -f ${out}.err; exit $$ec') % (cmd1, cmd2, _INCLUSION_STACK_SPLITTER)

    @override
    def get_link_command(self):
        return self.ld + self._get_link_args()

    @override
    def get_shared_link_command(self):
        return self.ld + '-shared ' + self._get_link_args()

    @override
    def get_static_library_command(self):
        flags = ''.join(config.get_item('cc_library_config', 'arflags'))
        return 'rm -f $out; %s %s $out $in' % (self.ar, flags)

    def _get_link_args(self):
        return ' -o ${out} ${intrinsic_linkflags} ${linkflags} ${target_linkflags} @${out}.rsp ${extra_linkflags}'

    @override
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


class CcToolChainMsvc(CcToolChain):
    """The build platform handles and gets the platform information."""

    def __init__(self):
        self.cc = 'cl.exe'
        self.cxx = 'cl.exe'
        self.ld = 'link.exe'
        self.ar = 'lib.exe'
        self.rc = 'rc.exe'
        self.cc_version = self._get_cc_version()

    def _get_cc_version(self):
        version = ''
        returncode, stdout, stderr = run_command(self.cc, shell=True)
        if returncode == 0:
            m = re.search(r'Compiler Version ([\d.]+)', stderr.strip())
            if m:
                version = m.group(1)
        if not version:
            console.fatal('Failed to obtain cc toolchain.')
        return version

    @staticmethod
    def get_cc_target_arch():
        """Get the cc target architecture."""
        cc = CcToolChain._get_cc_command('CC', 'gcc')
        returncode, stdout, stderr = run_command(cc + ' -dumpmachine', shell=True)
        if returncode == 0:
            return stdout.strip()
        return ''

    @override
    def is_kind_of(self, vendor):
        return vendor in ('msvc')

    @override
    def object_file_of(self, source_file):
        return source_file + '.obj'

    @override
    def executable_file_name(self, name):
        return name + '.exe'

    def filter_cc_flags(self, flag_list, language='c'):
        """Filter out the unrecognized compilation flags."""
        flag_list = var_to_list(flag_list)
        valid_flags, unrecognized_flags = [], []

        # cl.exe only report the first error option, so we must test flags one by one.
        for flag in flag_list:
            if flag.startswith('-'):
                testflag = '/' + flag[1:]
            else:
                testflag = flag
            cmd = ('"%s" /nologo /E /Zs /c /WX %s' % (self.cc, testflag))
            try:
                returncode, stdout, stderr = run_command(cmd, shell=False)
                if returncode == 0:
                    continue
                output = stdout + stderr
                # Example error messages:
                #   Command line error D8021 : invalid numeric argument '/Wzzz'
                if "'%s'" % testflag in output:
                    unrecognized_flags.append(flag)
                else:
                    valid_flags.append(flag)
            except OSError as e:
                console.fatal("filter_cc_flags error, cmd='%s', error='%s'" % (cmd, e))

        if unrecognized_flags:
            console.warning('config: Unrecognized %s flags: %s' % (
                    language, ', '.join(unrecognized_flags)))

        return valid_flags

    @override
    def get_compile_commands(self, build_dir, cppflags, is_dump):
        cc_config = config.get_section('cc_config')
        cflags, cxxflags = cc_config['cflags'], cc_config['cxxflags']
        cppflags = cc_config['cppflags'] + cppflags
        includes = cc_config['extra_incs']
        includes = includes + ['.', build_dir]
        includes = ' '.join(['-I%s' % inc for inc in includes])

        cc_command = ('%s /nologo /c /Fo${out} %s %s ${optimize} '
                      '${c_warnings} ${cppflags} %s ${includes} ${in}') % (
                              self.cc, ' '.join(cflags), ' '.join(cppflags), includes)
        cxx_command = ('%s /nologo /c -Fo${out} %s %s ${optimize} '
                       '${cxx_warnings} ${cppflags} %s ${includes} ${in}') % (
                               self.cxx, ' '.join(cxxflags), ' '.join(cppflags), includes)
        securecc_command = (cc_config['secretcc'] + ' ' + cxx_command)

        hdrs_command = self._hdrs_command(cxxflags, cppflags, includes)

        if is_dump:
            # When dumping compdb, a raw compile command without wrapper should be generated,
            # otherwise some tools can't handle it.
            return cc_command, cxx_command, securecc_command, hdrs_command
        template = self._cc_compile_command_wrapper_template('${out}.H')
        return template % cc_command, template % cxx_command, template % securecc_command, hdrs_command

    def _cc_compile_command_wrapper_template(self, inclusion_stack_file, cuda=False):
        return '%s'

    def _hdrs_command(self, flags, cppflags, includes):
        """
        Command to generate cc inclusion information file for header file to check dependency missing.
        See https://learn.microsoft.com/en-us/cpp/build/reference/showincludes-list-include-files for details.
        """
        # If there is not #include in the file, findstr will fail, use "|| ver>nul" to ignore the error.
        # https://stackoverflow.com/questions/22046780/whats-the-windows-command-shell-equivalent-of-bashs-true-command
        cmd = ('cmd.exe /c %s /nologo /c /E /Zs /TP /showIncludes %s %s /w ${cppflags} %s ${includes} ${in} 2>&1 >nul |'
               ' findstr "Note: including file" >${out} || ver>nul'% (
            self.cc, ' '.join(flags), ' '.join(cppflags), includes))

        # If the first cpp command fails, the second cpp command will be executed.
        # The error message of the first command should be completely ignored.
        return cmd

    @override
    def get_link_command(self):
        return self.ld + self._get_link_args()

    @override
    def get_shared_link_command(self):
        return self.ld + ' /DLL ' + self._get_link_args()

    @override
    def get_static_library_command(self):
        flags = ''.join(config.get_item('cc_library_config', 'arflags'))
        return '%s /nologo %s /OUT:$out $in' % (self.ar, flags)

    def _get_link_args(self):
        return ' /nologo /OUT:${out} ${intrinsic_linkflags} ${linkflags} ${target_linkflags} @${out}.rsp ${extra_linkflags}'


def default(bits):
    if os.name == 'nt':
        return CcToolChainMsvc()
    return CcToolChainGcc()
