# Copyright (c) 2016 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   July 12, 2016

"""
Implement go_library, go_binary and go_test. In addition, provide
a simple wrapper function go_package wrapping all sorts of go tar-
gets totally.
"""

from __future__ import absolute_import
from __future__ import print_function

import os
import re

from blade import build_manager
from blade import build_rules
from blade import config
from blade import console
from blade.target import Target
from blade.util import run_command, var_to_list


_package_re = re.compile(r'^\s*package\s+(\w+)\s*$')


class GoTarget(Target):
    """This class is the base of all go targets."""

    _go_os = None
    _go_arch = None

    def __init__(self,
                 name,
                 type,
                 srcs,
                 deps,
                 extra_goflags,
                 visibility,
                 tags,
                 kwargs):
        """Init the go target."""
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        extra_goflags = ' '.join(var_to_list(extra_goflags))

        super(GoTarget, self).__init__(
                name=name,
                type=type,
                srcs=srcs,
                src_exts=['go'],
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)

        self._set_go_package()
        self._init_go_environment()
        self.attr['extra_goflags'] = extra_goflags
        self._add_tags('lang:go')

    def _set_go_package(self):
        """
        Set the package path from the source path inside the workspace
        specified by GOPATH. All the go sources of the same package
        should be in the same directory.
        """
        srcs = [self._source_file_path(s) for s in self.srcs]
        dirs = {os.path.dirname(s) for s in srcs}
        if len(dirs) != 1:
            self.error('Go sources belonging to the same package should be in the same '
                       'directory. Sources: %s' % ', '.join(self.srcs))
            return
        go_home = config.get_item('go_config', 'go_home')
        go_module_enabled = config.get_item('go_config', 'go_module_enabled')
        go_module_relpath = config.get_item('go_config', 'go_module_relpath')
        if go_module_enabled and not go_module_relpath:
            self.attr['go_package'] = os.path.join("./", self.path)
        else:
            self.attr['go_package'] = os.path.relpath(self.path, os.path.join(go_home, 'src'))

    def _init_go_environment(self):
        if GoTarget._go_os is None and GoTarget._go_arch is None:
            go = config.get_item('go_config', 'go')
            returncode, stdout, stderr = run_command([go, 'env'])
            if returncode != 0:
                self.error('Failed to initialize go environment: %s' % stderr)
                return
            for line in stdout.splitlines():
                if line.startswith('GOOS='):
                    GoTarget._go_os = line.replace('GOOS=', '').strip('"')
                elif line.startswith('GOARCH='):
                    GoTarget._go_arch = line.replace('GOARCH=', '').strip('"')

    def _expand_deps_generation(self):
        build_targets = self.blade.get_build_targets()
        for dep in self.expanded_deps:  # pylint: disable=not-an-iterable
            d = build_targets[dep]
            d.attr['generate_go'] = True

    def _go_dependencies(self):
        targets = self.blade.get_build_targets()
        srcs = [self._source_file_path(s) for s in self.srcs]
        implicit_deps = []
        for key in self.deps:
            path = targets[key]._get_target_file('gopkg')
            if path:
                # There are two cases for go package(gopkg)
                #
                #   - gopkg produced by another go_library,
                #     the target file here is a path to the
                #     generated lib
                #
                #   - gopkg produced by a proto_library, the
                #     target file is a list of pb.go files
                implicit_deps += var_to_list(path)
        return srcs + implicit_deps

    def _go_target_path(self):
        """Return the full path of generate target file"""
        return self._target_file_path(self.name)

    def generate(self):
        implicit_deps = self._go_dependencies()
        output = self._go_target_path()
        variables = {'package': self.attr['go_package']}
        if self.attr['extra_goflags']:
            variables['extra_goflags'] = self.attr['extra_goflags']
        self.generate_build(self.attr['go_rule'], output,
                            implicit_deps=implicit_deps,
                            variables=variables)
        label = self.attr.get('go_label')
        if label:
            self._add_target_file(label, output)


class GoLibrary(GoTarget):
    """GoLibrary generates build rules for a go package."""

    def __init__(self, name, srcs, deps, visibility, tags, extra_goflags, kwargs):
        super(GoLibrary, self).__init__(
                name=name,
                type='go_library',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                extra_goflags=extra_goflags,
                kwargs=kwargs)
        self.attr['go_rule'] = 'gopackage'
        self.attr['go_label'] = 'gopkg'
        self._add_tags('type:library')

    def _go_target_path(self):  # Override
        """Return package object path according to the standard go directory layout."""
        go_home = config.get_item('go_config', 'go_home')
        return os.path.join(go_home, 'pkg',
                            '%s_%s' % (GoTarget._go_os, GoTarget._go_arch),
                            '%s.a' % self.attr['go_package'])


class GoBinary(GoTarget):
    """GoBinary generates build rules for a go command executable."""

    def __init__(self, name, srcs, deps, visibility, tags, extra_goflags, kwargs):
        super(GoBinary, self).__init__(
                name=name,
                type='go_binary',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                extra_goflags=extra_goflags,
                kwargs=kwargs)
        self.attr['go_rule'] = 'gocommand'
        self.attr['go_label'] = 'bin'
        self._add_tags('type:binary')


class GoTest(GoTarget):
    """GoTest generates build rules for a go test binary."""

    def __init__(self, name, srcs, deps, visibility, tags, testdata, extra_goflags, kwargs):
        super(GoTest, self).__init__(
                name=name,
                type='go_test',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                extra_goflags=extra_goflags,
                kwargs=kwargs)
        self.attr['go_rule'] = 'gotest'
        self.attr['testdata'] = var_to_list(testdata)
        self._add_tags('type:test')


def go_library(
        name,
        srcs,
        deps=[],
        extra_goflags=None,
        visibility=None,
        tags=[],
        **kwargs):
    build_manager.instance.register_target(GoLibrary(
        name=name,
        srcs=srcs,
        deps=deps,
        visibility=visibility,
        tags=tags,
        extra_goflags=extra_goflags,
        kwargs=kwargs))


def go_binary(
        name,
        srcs,
        deps=[],
        visibility=None,
        tags=[],
        extra_goflags=None,
        **kwargs):
    build_manager.instance.register_target(GoBinary(
            name=name,
            srcs=srcs,
            deps=deps,
            extra_goflags=extra_goflags,
            visibility=visibility,
            tags=tags,
            kwargs=kwargs))


def go_test(
        name,
        srcs,
        deps=[],
        visibility=None,
        tags=[],
        testdata=[],
        extra_goflags=None,
        **kwargs):
    build_manager.instance.register_target(GoTest(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            testdata=testdata,
            extra_goflags=extra_goflags,
            kwargs=kwargs))


def find_go_srcs(path):
    srcs, tests = [], []
    for name in os.listdir(path):
        if name.startswith('.') or not name.endswith('.go'):
            continue
        if os.path.isfile(os.path.join(path, name)):
            if name.endswith('_test.go'):
                tests.append(name)
            else:
                srcs.append(name)
    return srcs, tests


def extract_go_package(path):
    with open(path) as f:
        for line in f:
            m = _package_re.match(line)
            if m:
                return m.group(1)
    raise Exception('Failed to find package in %s' % path)


def go_package(
        name,
        deps=[],
        testdata=[],
        visibility=None,
        extra_goflags=None):
    path = build_manager.instance.get_current_source_path()
    srcs, tests = find_go_srcs(path)
    if not srcs and not tests:
        console.error('Empty go sources in %s' % path)
        return
    if srcs:
        main = False
        for src in srcs:
            package = extract_go_package(os.path.join(path, src))
            if package == 'main':
                main = True
                break
        if main:
            go_binary(name=name, srcs=srcs, deps=deps, visibility=visibility,
                      extra_goflags=extra_goflags)
        else:
            go_library(name=name, srcs=srcs, deps=deps, visibility=visibility,
                       extra_goflags=extra_goflags)
    if tests:
        go_test(name='%s_test' % name,
                srcs=tests,
                deps=deps,
                visibility=visibility,
                testdata=testdata,
                extra_goflags=extra_goflags)


build_rules.register_function(go_library)
build_rules.register_function(go_binary)
build_rules.register_function(go_test)
build_rules.register_function(go_package)
