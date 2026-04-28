# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
This is python targets module which generates python egg,
python library, python binary, python test.
"""


import os

from blade import build_manager
from blade import build_rules
from blade.target import Target
from blade.util import var_to_list


class PythonTarget(Target):
    """python target base class.

    """

    def __init__(self,
                 name,
                 type,
                 srcs,
                 deps,
                 base,
                 visibility,
                 tags,
                 kwargs):
        """Init method."""
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)

        super().__init__(
            name=name,
            type=type,
            srcs=srcs,
            src_exts=['py', 'py2', 'py3', 'egg', 'whl'],
            deps=deps,
            visibility=visibility,
            tags=tags,
            kwargs=kwargs)

        if base:
            if not base.startswith('//'):
                self.error('Invalid base directory %s. Option base should be a directory '
                           'starting with \'//\' from BLADE_ROOT directory.' % base)
                return
            self.attr['python_base'] = base[2:]

    def _expand_deps_generation(self):
        build_targets = self.blade.get_build_targets()
        for dep in self.expanded_deps:  # pylint: disable=not-an-iterable
            d = build_targets[dep]
            d.attr['generate_python'] = True

    def _vars(self):
        vars = {}
        basedir = self.attr.get('python_base')
        if basedir:
            vars['basedir'] = basedir
        return vars


class PythonLibrary(PythonTarget):
    """A python library target subclass.
    This class generates python library package.
    """

    def __init__(self,
                 name,
                 srcs,
                 deps,
                 base,
                 visibility,
                 tags,
                 kwargs):
        """Init method."""
        super().__init__(
                name=name,
                type='py_library',
                srcs=srcs,
                deps=deps,
                base=base,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)
        self._add_tags('lang:py', 'type:library')

    def _pylib(self):
        if not self.srcs:
            return ''
        output = self._target_file_path(self.name + '.pylib')
        inputs = [self._source_file_path(s) for s in self.srcs]
        vars = self._vars()
        self.generate_build('pythonlibrary', output, inputs=inputs, variables=vars)
        self._add_target_file('pylib', output)
        return output

    def generate(self):
        self._pylib()


class PrebuiltPythonLibrary(PythonTarget):
    def __init__(self,
                 name,
                 srcs,
                 deps,
                 visibility,
                 tags,
                 base,
                 kwargs):
        """Init method."""
        super().__init__(
                name=name,
                type='prebuilt_py_library',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                base=base,
                kwargs=kwargs)
        self._add_tags('lang:py', 'type:library', 'type:prebuilt')
        if base:
            self.error("Prebuilt py_library doesn't support base")
        if len(self.srcs) != 1:
            self.error('There can only be 1 file in prebuilt py_library')
        src = self.srcs[0]
        if not src.endswith('.egg') and not src.endswith('.whl'):
            self.error(
                    'Invalid src "%s", prebuilt py_library only support egg and whl' % src)

    def generate(self):
        self._add_target_file('pylib', self._source_file_path(self.srcs[0]))


def py_library(name=None,
               srcs=[],
               deps=[],
               visibility=None,
               tags=[],
               base=None,
               prebuilt=None,
               **kwargs):
    """python library."""
    if prebuilt:
        target = PrebuiltPythonLibrary(
                name=name,
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                base=base,
                kwargs=kwargs)
    else:
        target = PythonLibrary(
                name=name,
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                base=base,
                kwargs=kwargs)

    build_manager.instance.register_target(target)


build_rules.register_function(py_library)


class PythonBinary(PythonLibrary):
    """A python binary target subclass.
    This class generates python binary package.
    """

    def __init__(self,
                 name,
                 srcs,
                 deps,
                 visibility,
                 tags,
                 main,
                 base,
                 exclusions,
                 kwargs):
        """Init method."""
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)

        super().__init__(
                name=name,
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                base=base,
                kwargs=kwargs)

        self.type = 'py_binary'
        self.attr['run_in_shell'] = True
        if main:
            self.attr['main'] = main
        else:
            if len(srcs) == 1:
                self.attr['main'] = srcs[0]
            else:
                self.error(
                    'The entry file must be specified by the "main" '
                    'argument if there are more than one srcs')
        self.attr['exclusions'] = exclusions
        self._add_tags('type:binary')

    def _get_entry(self):
        main = self.attr['main']
        full_path = os.path.normpath(os.path.join(self.path, main))[:-3]
        base_path = self.attr.get('python_base', '')
        rel_path = os.path.relpath(full_path, base_path)
        return rel_path.replace('/', '.')

    def generate(self):
        output = self._target_file_path(self.name)
        pylib = self._pylib()
        inputs = [pylib] if pylib else []
        targets = self.blade.get_build_targets()
        for key in self.expanded_deps:  # pylint: disable=not-an-iterable
            dep = targets[key]
            pylib = dep._get_target_file('pylib')
            if pylib:
                inputs.append(pylib)
            # TODO(wentingli): Add other dependencies if needed
        vars = self._vars()
        vars['mainentry'] = self._get_entry()
        vars['exclusions'] = ','.join(self.attr['exclusions'])
        self.generate_build('pythonbinary', output, inputs=inputs, variables=vars)
        self._add_default_target_file('bin', output)


def py_binary(name=None,
              srcs=[],
              deps=[],
              visibility=None,
              tags=[],
              main=None,
              base=None,
              exclusions=[],
              **kwargs):
    """python binary."""
    target = PythonBinary(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            main=main,
            base=base,
            exclusions=exclusions,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(py_binary)


class PythonTest(PythonBinary):
    """A python test target subclass.
    This class generates python test.
    """

    def __init__(self,
                 name,
                 srcs,
                 deps,
                 visibility,
                 tags,
                 main,
                 base,
                 testdata,
                 kwargs):
        """Init method."""
        super().__init__(
                name=name,
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                main=main,
                base=base,
                exclusions=[],
                kwargs=kwargs)
        self.type = 'py_test'
        self.attr['testdata'] = testdata
        self._add_tags('type:test')


def py_test(name=None,
            srcs=[],
            deps=[],
            visibility=None,
            tags=[],
            main=None,
            base=None,
            testdata=[],
            **kwargs):
    """python test."""
    target = PythonTest(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=[],
            main=main,
            base=base,
            testdata=testdata,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(py_test)
