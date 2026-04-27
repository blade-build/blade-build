# Copyright (c) 2012 iQIYI Inc.
# Copyright (c) 2013 Tencent Inc.
# Copyright (c) 2014 Huahang Liu
#
# All rights reserved.
#
# Author: Jingxu Chen <chenjingxu@qiyi.com>
#         Feng Chen <chen3feng@gmail.com>
#         Huahang Liu <liuhuahang@zerus.co>
#
# Date:   June 28, 2014


"""
The module defines fbthrift_library target to generate code in
different languages from .thrift file.
"""


import os

from blade import build_manager
from blade import build_rules
from blade import config
from blade.cc_targets import CcTarget
from blade.thrift_helper import FBThriftHelper
from blade.util import var_to_list


class FBThriftLibrary(CcTarget):
    """A fbthrift library target derived from CcTarget."""
    def __init__(self,
                 name,
                 srcs,
                 deps,
                 optimize,
                 visibility,
                 tags,
                 deprecated,
                 kwargs):
        srcs = var_to_list(srcs)
        super(FBThriftLibrary, self).__init__(
                name=name,
                type='fbthrift_library',
                srcs=srcs,
                src_exts=['thrift'],
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning='',
                defs=[],
                incs=[],
                export_incs=[],
                optimize=optimize,
                linkflags=None,
                extra_cppflags=[],
                extra_linkflags=[],
                kwargs=kwargs)

        fbthrift_config = config.get_section('fbthrift_config')
        fbthrift_libs = var_to_list(fbthrift_config['fbthrift_libs'])

        # Add implicit deps rule to thrift libraries.
        self._add_implicit_library(fbthrift_libs)

        # Link all the symbols by default
        self.attr['link_all_symbols'] = True

        # For each thrift file initialize a FBThriftHelper, which will be used
        # to get the source files generated from thrift file.
        self.fbthrift_helpers = {}
        for src in srcs:
            self.fbthrift_helpers[src] = FBThriftHelper(
                os.path.join(self.path, src))

    def _thrift_gen_cpp_files(self, src):
        """Get the c++ files generated from thrift file."""
        return [self._target_file_path(f)
                for f in self.fbthrift_helpers[src].get_generated_cpp_files()]

    def _thrift_gen_cpp2_files(self, src):
        """Get the c++ files generated from thrift file."""
        return [self._target_file_path(f)
                for f in self.fbthrift_helpers[src].get_generated_cpp2_files()]

    def generate(self):
        self.error('FIXME: fbthrift is still not supported by the ninja backend.')
        # (don't forget `generated_hdrs`)


def fbthrift_library(name=None,
                     srcs=[],
                     deps=[],
                     optimize=None,
                     visibility=None,
                     tags=[],
                     deprecated=False,
                     **kwargs):
    """fbthrift_library target."""
    fbthrift_library_target = FBThriftLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            optimize=optimize,
            visibility=visibility,
            tags=tags,
            deprecated=deprecated,
            kwargs=kwargs)
    build_manager.instance.register_target(fbthrift_library_target)


build_rules.register_function(fbthrift_library)
