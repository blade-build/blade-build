# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: Feng Chen <phongchen@tencent.com>


"""
Define swig_library target.
"""


import os

from blade import build_manager
from blade import build_rules
from blade.cc_targets import CcTarget


class SwigLibrary(CcTarget):
    """This class is used to build swig library."""

    def __init__(self,
                 name,
                 srcs,
                 deps,
                 visibility,
                 tags,
                 warning,
                 java_package,
                 java_lib_packed,
                 optimize,
                 extra_swigflags,
                 kwargs):
        super().__init__(
                name=name,
                type='swig_library',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning=warning,
                defs=[],
                incs=[],
                export_incs=[],
                optimize=optimize,
                linkflags=None,
                extra_cppflags=[],
                extra_linkflags=[],
                kwargs=kwargs)
        self.attr['cpperraswarn'] = warning
        self.attr['java_package'] = java_package
        self.attr['java_lib_packed'] = java_lib_packed
        self.attr['extra_swigflags'] = extra_swigflags
        self._add_tags('lang:swig', 'type:library')

    def _expand_deps_generation(self):
        build_targets = self.blade.get_build_targets()
        for dep in self.expanded_deps:  # pylint: disable=not-an-iterable
            d = build_targets[dep]
            if d.type == 'proto_library':
                d.attr['generate_php'] = True

    def _pyswig_gen_python_file(self, path, src):
        """Generate swig python file for python."""
        swig_name = src[:-2]
        return os.path.join(self.build_dir, path, '%s.py' % swig_name)

    def _pyswig_gen_file(self, path, src):
        """Generate swig cxx files for python."""
        swig_name = src[:-2]
        return os.path.join(self.build_dir, path, '%s_pywrap.cxx' % swig_name)

    def _javaswig_gen_file(self, path, src):
        """Generate swig cxx files for java."""
        swig_name = src[:-2]
        return os.path.join(self.build_dir, path, '%s_javawrap.cxx' % swig_name)

    def _phpswig_gen_file(self, path, src):
        """Generate swig cxx files for php."""
        swig_name = src[:-2]
        return os.path.join(self.build_dir, path, '%s_phpwrap.cxx' % swig_name)

    def _swig_extract_dependency_files(self, src):
        dep = []
        with open(src) as f:
            for line in f:
                if line.startswith('#include') or line.startswith('%include'):
                    line = line.split(' ')[1].strip("""'"\r\n""")
                    if not ('<' in line or line in dep):
                        dep.append(line)
        return [i for i in dep if os.path.exists(i)]

    def generate(self):
        self.error('Not implemented')


def swig_library(
        name,
        srcs=[],
        deps=[],
        visibility=None,
        tags=[],
        warning='',
        java_package='',
        java_lib_packed=False,
        optimize=None,
        extra_swigflags=[],
        **kwargs):
    """swig_library target."""
    target = SwigLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            java_package=java_package,
            java_lib_packed=java_lib_packed,
            optimize=optimize,
            extra_swigflags=extra_swigflags,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(swig_library)
