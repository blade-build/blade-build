# Copyright (c) 2012 iQIYI Inc.
# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: Jingxu Chen <chenjingxu@qiyi.com>
#         Feng Chen <chen3feng@gmail.com>
# Date:   October 13, 2012


"""
The module defines thrift_library target to generate code in
different languages from .thrift file.
"""


import os

from blade import build_manager
from blade import build_rules
from blade import config
from blade.cc_targets import CcTarget
from blade.thrift_helper import ThriftHelper
from blade.util import var_to_list


# TODO(chen3feng): Support java generation
class ThriftLibrary(CcTarget):
    """A thrift library target derived from CcTarget."""

    def __init__(
            self,
            name,
            srcs,
            deps,
            visibility,
            tags,
            optimize,
            deprecated,
            kwargs):
        srcs = var_to_list(srcs)
        super().__init__(
                name=name,
                type='thrift_library',
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

        thrift_libs = config.get_item('thrift_config', 'thrift_libs')
        # Hardcode deps rule to thrift libraries.
        self._add_implicit_library(thrift_libs)

        # Link all the symbols by default
        self.attr['link_all_symbols'] = True
        self.attr['deprecated'] = deprecated
        self._add_tags('lang:thrift', 'type:library')

        # For each thrift file initialize a ThriftHelper, which will be used
        # to get the source files generated from thrift file.
        headers = []
        self.thrift_helpers = {}
        for src in self.srcs:
            self.thrift_helpers[src] = ThriftHelper(self.path, src)
            thrift_files = self._thrift_gen_cpp_files(src)
            headers += [h for h in thrift_files if h.endswith('.h')]
        self.attr['generated_hdrs'] = headers

    def _thrift_gen_cpp_files(self, src):
        """Get the c++ files generated from thrift file."""
        files = []
        for f in self.thrift_helpers[src].get_generated_cpp_files():
            files.append(self._target_file_path(f))
        return files

    def _thrift_gen_py_files(self, src):
        """Get the python files generated from thrift file."""
        files = []
        for f in self.thrift_helpers[src].get_generated_py_files():
            files.append(self._target_file_path(f))
        return files

    def _thrift_gen_java_files(self, src):
        """Get the java files generated from thrift file."""
        files = []
        for f in self.thrift_helpers[src].get_generated_java_files():
            files.append(self._target_file_path(f))
        return files

    def generate(self):
        if not self.srcs:
            return
        target_dir = os.path.join(self.build_dir, self.path)
        sources = []
        for src in self.srcs:
            thrift_files = self._thrift_gen_cpp_files(src)
            self.generate_build('thrift', thrift_files, inputs=self._source_file_path(src))
            thrift_cpp_sources = [s for s in thrift_files if s.endswith('.cpp')]
            sources += [os.path.relpath(s, target_dir) for s in thrift_cpp_sources]
        objs = self._generated_cc_objects(sources, generated_headers=self.attr['generated_hdrs'])
        self._cc_library(objs)


def thrift_library(
        name,
        srcs=None,
        deps=None,
        visibility=None,
        tags=None,
        optimize=None,
        deprecated=False,
        **kwargs):
    """thrift_library target."""
    thrift_library_target = ThriftLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            optimize=optimize,
            deprecated=deprecated,
            kwargs=kwargs)
    build_manager.instance.register_target(thrift_library_target)


build_rules.register_function(thrift_library)
