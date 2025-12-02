# Copyright (c) 2015 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   November 25, 2015

"""
Implement scala_library, scala_fat_library and scala_test.
"""

from __future__ import absolute_import
from __future__ import print_function

import os

from blade import build_manager
from blade import build_rules
from blade import config
from blade import console
from blade.java_targets import JavaTargetMixIn
from blade.target import Target
from blade.util import var_to_list


class ScalaTarget(Target, JavaTargetMixIn):
    """A scala target subclass.

    This class is the base of all scala targets.

    """

    def __init__(self,
                 name,
                 type,
                 srcs,
                 deps,
                 visibility,
                 tags,
                 resources,
                 source_encoding,
                 warnings,
                 kwargs):
        """Init method.

        Init the scala target.

        """
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        resources = var_to_list(resources)

        super(ScalaTarget, self).__init__(
                name=name,
                type=type,
                srcs=srcs,
                src_exts=['scala', 'java'],
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)
        self._process_resources(resources)
        if source_encoding:
            self.attr['source_encoding'] = source_encoding
        if warnings:
            self.attr['warnings'] = warnings
        self._add_tags('lang:scala')

    def _expand_deps_generation(self):
        self._expand_deps_java_generation()

    def _get_java_pack_deps(self):
        return self._get_pack_deps()

    def scalac_flags(self):
        flags = []
        scala_config = config.get_section('scala_config')
        target_platform = scala_config['target_platform']
        if target_platform:
            flags.append('-target:%s' % target_platform)
        warnings = self.attr.get('warnings')
        if warnings:
            flags.append(warnings)
        global_warnings = scala_config['warnings']
        if global_warnings:
            flags.append(global_warnings)
        return flags

    def _scala_full_path_srcs(self):
        """Expand srcs to full path"""
        srcs = []
        for s in self.srcs:
            sp = self._source_file_path(s)
            # If it doesn't exist, consider it as a generated file in target dir
            srcs.append(sp if os.path.exists(sp) else self._target_file_path(s))
        return srcs

    def _generate_jar(self):
        self._generate_sources_dir_for_coverage()
        srcs = self._scala_full_path_srcs()
        resources = self._generate_resources()
        jar = self._target_file_path(self.name + '.jar')
        if srcs and resources:
            classes_jar = self._target_file_path(self.name + '__classes__.jar')
            scalacflags = self.scalac_flags()
            self._build_jar(classes_jar, inputs=srcs, scala=True, scalacflags=scalacflags)
            self.generate_build('javajar', jar, inputs=[classes_jar] + resources)
        elif srcs:
            scalacflags = self.scalac_flags()
            self._build_jar(jar, inputs=srcs, scala=True, scalacflags=scalacflags)
        elif resources:
            self.generate_build('javajar', jar, inputs=resources)
        else:
            jar = ''
        if jar:
            self._add_target_file('jar', jar)
        return jar


class ScalaLibrary(ScalaTarget):
    """ScalaLibrary"""

    def __init__(
            self,
            name,
            srcs,
            deps,
            visibility,
            tags,
            resources,
            source_encoding,
            warnings,
            exported_deps,
            provided_deps,
            coverage,
            kwargs):
        exported_deps = var_to_list(exported_deps)
        provided_deps = var_to_list(provided_deps)
        all_deps = var_to_list(deps) + exported_deps + provided_deps
        super(ScalaLibrary, self).__init__(
                name=name,
                type='scala_library',
                srcs=srcs,
                deps=all_deps,
                visibility=visibility,
                tags=tags,
                resources=resources,
                source_encoding=source_encoding,
                warnings=warnings,
                kwargs=kwargs)
        self.attr['exported_deps'] = self._unify_deps(exported_deps)
        self.attr['provided_deps'] = self._unify_deps(provided_deps)
        self.attr['jacoco_coverage'] = coverage and bool(srcs)
        self._add_tags('type:library')

    def generate(self):
        jar = self._generate_jar()
        if jar:
            self._add_default_target_file('jar', jar)


class ScalaFatLibrary(ScalaTarget):
    """ScalaFatLibrary"""

    def __init__(
            self,
            name,
            srcs,
            deps,
            visibility,
            tags,
            resources,
            source_encoding,
            warnings,
            exclusions,
            kwargs):
        super(ScalaFatLibrary, self).__init__(
                name=name,
                type='scala_fat_library',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                resources=resources,
                source_encoding=source_encoding,
                warnings=warnings,
                kwargs=kwargs)
        if exclusions:
            self._set_pack_exclusions(exclusions)
        self._add_tags('type:library', 'type:fatjar')

    def generate(self):
        jar = self._generate_fat_jar()
        self._add_default_target_file('fatjar', jar)


class ScalaTest(ScalaFatLibrary):
    """ScalaTest"""

    def __init__(
            self,
            name,
            srcs,
            deps,
            visibility,
            tags,
            resources,
            source_encoding,
            warnings,
            exclusions,
            testdata,
            kwargs):
        super(ScalaTest, self).__init__(
                name=name,
                srcs=srcs,
                deps=deps,
                resources=resources,
                visibility=visibility,
                tags=tags,
                source_encoding=source_encoding,
                warnings=warnings,
                exclusions=exclusions,
                kwargs=kwargs)
        self.type = 'scala_test'
        self.attr['testdata'] = var_to_list(testdata)
        self._add_tags('type:test')

        if not self.srcs:
            self.warning('Empty scala test sources.')

        scalatest_libs = config.get_item('scala_test_config', 'scalatest_libs')
        if scalatest_libs:
            self._add_implicit_library(scalatest_libs)
        else:
            console.warning('Config: "scala_test_config.scalatest_libs" is not configured')

    def generate(self):
        if not self.srcs:
            return
        jar = self._generate_jar()
        output = self._target_file_path(self.name)
        dep_jars, maven_jars = self._get_test_deps()
        vars = {
            'packages_under_test': self._packages_under_test()
        }
        self.generate_build('scalatest', output, inputs=[jar] + dep_jars + maven_jars, variables=vars)


def scala_library(name=None,
                  srcs=[],
                  deps=[],
                  resources=[],
                  visibility=None,
                  tags=[],
                  source_encoding=None,
                  warnings=None,
                  exported_deps=[],
                  provided_deps=[],
                  coverage=True,
                  **kwargs):
    """Define scala_library target."""
    target = ScalaLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            resources=resources,
            source_encoding=source_encoding,
            warnings=warnings,
            exported_deps=exported_deps,
            provided_deps=provided_deps,
            coverage=coverage,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


def scala_fat_library(name=None,
                      srcs=[],
                      deps=[],
                      resources=[],
                      visibility=None,
                      tags=[],
                      source_encoding=None,
                      warnings=None,
                      exclusions=[],
                      **kwargs):
    """Define scala_fat_library target."""
    target = ScalaFatLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            resources=resources,
            visibility=visibility,
            tags=tags,
            source_encoding=source_encoding,
            warnings=warnings,
            exclusions=exclusions,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


def scala_test(name=None,
               srcs=None,
               deps=[],
               resources=[],
               visibility=None,
               tags=[],
               source_encoding=None,
               warnings=None,
               exclusions=[],
               testdata=[],
               **kwargs):
    """Build a scala test target
    Args:
        Most attributes are similar to java_test.
    """
    target = ScalaTest(name=name,
                       srcs=srcs,
                       deps=deps,
                       resources=resources,
                       visibility=visibility,
                       tags=tags,
                       source_encoding=source_encoding,
                       warnings=warnings,
                       exclusions=exclusions,
                       testdata=testdata,
                       kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(scala_library)
build_rules.register_function(scala_fat_library)
build_rules.register_function(scala_test)
