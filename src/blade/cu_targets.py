# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: LI Yi <sincereli@tencent.com>
# Created:   September 27, 2013


"""
This module defines cu_library, cu_binary and cu_test rules
for cuda development.
"""


import os

from blade import build_manager
from blade import build_rules
from blade import config
from blade import console
from blade.cc_targets import CcTarget
from blade.util import var_to_list


# See https://docs.nvidia.com/cuda/cuda-compiler-driver-nvcc/index.html#supported-input-file-suffixes
_SOURCE_FILE_EXTS = {'cu', 'c', 'cc', 'cxx', 'cpp', 'ptx'}


class CuTarget(CcTarget):
    """This class is derived from CcTarget and is the base class
    of cu_library, cu_binary etc.

    """

    def __init__(self,
                 name,
                 type,
                 srcs,
                 cuda_path,
                 deps,
                 visibility,
                 tags,
                 warning,
                 defs,
                 incs,
                 extra_cppflags,
                 extra_cuflags,
                 extra_linkflags,
                 kwargs):
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        extra_cppflags = var_to_list(extra_cppflags)
        extra_cuflags = var_to_list(extra_cuflags)
        extra_linkflags = var_to_list(extra_linkflags)

        super().__init__(
                name=name,
                type=type,
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                export_incs=[],
                optimize=None,
                linkflags=None,
                extra_cppflags=extra_cppflags,
                extra_linkflags=extra_linkflags,
                kwargs=kwargs,
                src_exts=_SOURCE_FILE_EXTS,
                cmd='')
        self.cuda_path = self._get_cuda_path(cuda_path)
        self.attr['extra_cuflags'] = var_to_list(extra_cuflags)
        cmd = os.environ.get('NVCC')
        if self.cuda_path:
            cmd = os.path.join(self.cuda_path, 'bin/nvcc')
        if not cmd:
            cmd = 'nvcc'
        self.cmd = cmd
        self._add_tags('lang:cu')

    def _get_cuda_path(self, cuda_path):
        """Get cuda_path with priority target's cuda_path > global cuda_path.

        cuda_path should start with // and will get trimmed in this phase.
        """
        global_cuda_path = config.get_section('cuda_config')['cuda_path']
        if global_cuda_path and not global_cuda_path.startswith('//'):
            console.fatal(
                'global cuda_path in cuda_config %s should be '
                'empty or start with //' % global_cuda_path)
        if cuda_path and not cuda_path.startswith('//'):
            console.fatal('targets: %s cuda_path %s should start with //' %
                          (self.fullname, cuda_path))
        if not cuda_path:
            cuda_path = global_cuda_path
        if cuda_path:
            cuda_path = cuda_path[2:]
        return cuda_path

    def _get_cu_flags(self):
        """Return the nvcc flags according to the BUILD file and other configs."""
        nvcc_flags = self.attr.get('extra_cuflags', [])
        return nvcc_flags

    def _get_cuda_include(self):
        include_list = []
        if self.cuda_path:
            include_list.append('%s/include' % self.cuda_path)
        else:
            cuda_path = os.environ.get('CUDA_PATH')
            if cuda_path:
                include_list.append('%s/include' % cuda_path)
                include_list.append('%s/samples/common/inc' % cuda_path)
        return include_list

    def _get_cu_vars(self):
        vars = self._get_cc_vars()
        cuda_incs = self._get_cuda_include()
        vars["includes"] = vars.get("includes", "") \
            + ' ' + ' '.join(['-I%s' % inc for inc in cuda_incs])
        vars['cmd'] = self.cmd

        vars['cuflags'] = ' '.join(self._get_cu_flags())
        cppflags = vars['cppflags'].split(' ') if vars.get('cppflags') else []

        vars['cuflags'] += ' ' + ' '.join(
            ['-Xcompiler %s' % flag for flag in cppflags]
        )

        return vars

    def _cuda_objects(self, expanded_srcs, generated_headers=None):
        vars = self._get_cu_vars()
        order_only_deps = []
        order_only_deps += self._cc_compile_deps()
        if generated_headers and len(generated_headers) > 1:
            order_only_deps += generated_headers
        implicit_deps = []

        objs_dir = self._target_file_path(self.name + '.objs')
        objs = []
        for src, full_src in expanded_srcs:
            obj = os.path.join(objs_dir, src + '.o')
            self.generate_build("cudacc", obj, inputs=full_src,
                                implicit_deps=implicit_deps,
                                order_only_deps=order_only_deps,
                                variables=vars, clean=[],
                                )
            objs.append(obj)
        self._remove_on_clean(objs_dir)

        # If cuda_path is in this repository, the {cuda_path}/include will throw
        # inclusion check error if header not in any target.
        if 'inclusion_check_info_file' in self.data:
            return objs, self._generate_inclusion_check(objs_dir, objs, vars, order_only_deps)
        return objs, None

    def _cuda_library(self, objs, inclusion_check_result=None):
        # TODO ar command flag is different with cc, such as rcs
        self._static_cc_library(objs, inclusion_check_result)
        if self.attr.get('generate_dynamic'):
            self._dynamic_cuda_library(objs, inclusion_check_result)

    def _dynamic_cuda_library(self, objs, inclusion_check_result):
        output = self._target_file_path('lib%s.so' % self.name)
        target_linkflags = self._generate_link_flags()
        sys_libs, usr_libs, incchk_deps = self._dynamic_dependencies()
        if inclusion_check_result:
            incchk_deps.append(inclusion_check_result)
        self._cc_link(output, 'cudasolink', objs=objs, deps=usr_libs, sys_libs=sys_libs,
                      order_only_deps=incchk_deps,
                      target_linkflags=target_linkflags,
                      cmd=self.cmd)
        self._add_target_file('so', output)


class CuLibrary(CuTarget):
    """This class is derived from CuTarget and generates the cu_library
    rules according to user options.

    """

    def __init__(self,
                 name,
                 srcs,
                 hdrs,
                 cuda_path,
                 deps,
                 visibility,
                 tags,
                 warning,
                 defs,
                 incs,
                 link_all_symbols,
                 extra_cppflags,
                 extra_cuflags,
                 extra_linkflags,
                 kwargs):
        super().__init__(
                name=name,
                type='cu_library',
                srcs=srcs,
                cuda_path=cuda_path,
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                extra_cppflags=extra_cppflags,
                extra_cuflags=extra_cuflags,
                extra_linkflags=extra_linkflags,
                kwargs=kwargs)
        self.attr['link_all_symbols'] = link_all_symbols
        self._add_tags('type:library')
        self._set_hdrs(hdrs)

    def _before_generate(self):  # override
        """Override"""
        self._write_inclusion_check_info()
        self._check_binary_link_only()

    def generate(self):
        self._check_deprecated_deps()
        objs, inclusion_check_result = self._cuda_objects(self.attr['expanded_srcs'])
        # Don't generate library file for header only library.
        if objs:
            self._cuda_library(objs, inclusion_check_result)


def cu_library(name=None,
               srcs=None,
               hdrs=None,
               cuda_path=None,
               deps=None,
               visibility=None,
               tags=None,
               warning='yes',
               defs=None,
               incs=None,
               link_all_symbols=False,
               extra_cppflags=None,
               extra_cuflags=None,
               extra_linkflags=None,
               **kwargs):
    target = CuLibrary(
            name,
            srcs=srcs,
            hdrs=hdrs,
            cuda_path=cuda_path,
            deps=deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            defs=defs,
            incs=incs,
            link_all_symbols=link_all_symbols,
            extra_cppflags=extra_cppflags,
            extra_cuflags=extra_cuflags,
            extra_linkflags=extra_linkflags,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(cu_library)


class CuBinary(CuTarget):
    """This class is derived from CuTarget and generates the cu_binary
    rules according to user options.

    """

    def __init__(self,
                 name,
                 srcs,
                 cuda_path,
                 deps,
                 visibility,
                 tags,
                 warning,
                 defs,
                 incs,
                 extra_cppflags,
                 extra_cuflags,
                 extra_linkflags,
                 kwargs):
        super().__init__(
                name=name,
                type='cu_binary',
                srcs=srcs,
                cuda_path=cuda_path,
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                extra_cppflags=extra_cppflags,
                extra_cuflags=extra_cuflags,
                extra_linkflags=extra_linkflags,
                kwargs=kwargs)
        self._add_tags('type:binary')

    def generate(self):
        self._check_deprecated_deps()
        objs, inclusion_check_result = self._cuda_objects(self.attr['expanded_srcs'])
        # Don't generate library file for header only library.
        self._cuda_binary(objs, inclusion_check_result, self.attr.get('dynamic_link', False))

    def _generate_cuda_binary_link_flags(self, dynamic_link):
        # TODO to be implemented
        return []

    def _cuda_binary(self, objs, inclusion_check_result, dynamic_link):
        implicit_deps = None
        target_linkflags = self._generate_cuda_binary_link_flags(dynamic_link)
        if dynamic_link:
            sys_libs, usr_libs, incchk_deps = self._dynamic_dependencies()
        else:
            sys_libs, usr_libs, link_all_symbols_libs, incchk_deps = self._static_dependencies()
            if link_all_symbols_libs:
                target_linkflags += self._generate_link_all_symbols_link_flags(link_all_symbols_libs)
                implicit_deps = link_all_symbols_libs

        # Using incchk as order_only_deps to avoid relink when only inclusion check is done.
        order_only_deps = incchk_deps
        if inclusion_check_result:
            order_only_deps.append(inclusion_check_result)

        output = self._target_file_path(self.name)
        self._cc_link(output, 'cudalink', objs=objs, deps=usr_libs,
                      sys_libs=sys_libs,
                      linker_scripts=self.attr.get('lds_fullpath'),
                      version_scripts=self.attr.get('vers_fullpath'),
                      target_linkflags=target_linkflags,
                      implicit_deps=implicit_deps,
                      order_only_deps=order_only_deps,
                      cmd=self.cmd)
        self._add_default_target_file('bin', output)
        self._remove_on_clean(self._target_file_path(self.name + '.runfiles'))

    def _before_generate(self):  # override
        """Override"""
        self._write_inclusion_check_info()


def cu_binary(name=None,
              srcs=None,
              cuda_path=None,
              deps=None,
              visibility=None,
              tags=None,
              warning='yes',
              defs=None,
              incs=None,
              extra_cppflags=None,
              extra_cuflags=None,
              extra_linkflags=None,
              **kwargs):
    target = CuBinary(
            name=name,
            srcs=srcs,
            cuda_path=cuda_path,
            deps=deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            defs=defs,
            incs=incs,
            extra_cppflags=extra_cppflags,
            extra_cuflags=extra_cuflags,
            extra_linkflags=extra_linkflags,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(cu_binary)


class CuTest(CuBinary):
    """This class is derived from CuBinary and generates the cu_test
    rules according to user options.

    """

    def __init__(self,
                 name,
                 srcs,
                 cuda_path,
                 deps,
                 visibility,
                 tags,
                 warning,
                 defs,
                 incs,
                 extra_cppflags,
                 extra_cuflags,
                 extra_linkflags,
                 testdata,
                 always_run,
                 exclusive,
                 kwargs):
        # pylint: disable=too-many-locals
        super().__init__(
                name=name,
                srcs=srcs,
                cuda_path=cuda_path,
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                extra_cppflags=extra_cppflags,
                extra_cuflags=extra_cuflags,
                extra_linkflags=extra_linkflags,
                kwargs=kwargs)
        self._add_tags('lang:cu')
        self.type = 'cu_test'
        self.attr['testdata'] = var_to_list(testdata)
        self.attr['always_run'] = always_run
        self.attr['exclusive'] = exclusive

        cc_test_config = config.get_section('cc_test_config')
        gtest_lib = var_to_list(cc_test_config['gtest_libs'])
        gtest_main_lib = var_to_list(cc_test_config['gtest_main_libs'])

        # Hardcode deps rule to thirdparty gtest main lib.
        self._add_implicit_library(gtest_lib)
        self._add_implicit_library(gtest_main_lib)


def cu_test(
        name,
        srcs=None,
        cuda_path=None,
        deps=None,
        visibility=None,
        tags=None,
        warning='yes',
        defs=None,
        incs=None,
        extra_cppflags=None,
        extra_cuflags=None,
        extra_linkflags=None,
        testdata=None,
        always_run=False,
        exclusive=False,
        **kwargs):
    target = CuTest(
            name=name,
            srcs=srcs,
            cuda_path=cuda_path,
            deps=deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            defs=defs,
            incs=incs,
            extra_cppflags=extra_cppflags,
            extra_cuflags=extra_cuflags,
            extra_linkflags=extra_linkflags,
            testdata=testdata,
            always_run=always_run,
            exclusive=exclusive,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(cu_test)
