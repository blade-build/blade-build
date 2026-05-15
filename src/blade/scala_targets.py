# Copyright (c) 2015 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   November 25, 2015

"""
Implement scala_library, scala_fat_library and scala_test.
"""


import os

from blade import build_manager
from blade import build_rules
from blade import config
from blade.blade_types import StrOrListOpt
from blade.java_targets import JavaTargetMixIn
from blade.target import Target
from blade.util import var_to_list, var_to_list_or_none


class ScalaTarget(Target, JavaTargetMixIn):
    """A scala target subclass.

    This class is the base of all scala targets.

    """

    def __init__(self,
                 name: str | None,
                 type: str,
                 srcs: StrOrListOpt,
                 deps: StrOrListOpt,
                 visibility: StrOrListOpt,
                 tags: StrOrListOpt,
                 resources: StrOrListOpt,
                 source_encoding: str | None,
                 warnings: str | None,
                 kwargs: dict[str, object]):
        """Init method.

        Init the scala target.

        """
        # Normalize BUILD-file-friendly StrOrList unions to list[str] once,
        # right at the top; Target.__init__ below sees layer-2 shapes.
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        resources = var_to_list(resources)
        tags = var_to_list(tags)
        visibility = var_to_list_or_none(visibility)

        super().__init__(
                name=name,
                type=type,
                srcs=srcs,
                src_exts=['scala', 'java'],
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)
        self._process_resources(resources)
        # Pre-expand resource directories so that changes to files inside
        # the directory are captured in the target's fingerprint.
        if self.attr['resources']:
            self.attr['expanded_resources'] = self._process_regular_resources(
                self.attr['resources'])
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
            name: str | None,
            srcs: StrOrListOpt,
            deps: StrOrListOpt,
            visibility: StrOrListOpt,
            tags: StrOrListOpt,
            resources: StrOrListOpt,
            source_encoding: str | None,
            warnings: str | None,
            exported_deps: StrOrListOpt,
            provided_deps: StrOrListOpt,
            coverage: bool,
            kwargs: dict[str, object]):
        exported_deps = var_to_list(exported_deps)
        provided_deps = var_to_list(provided_deps)
        all_deps = var_to_list(deps) + exported_deps + provided_deps
        super().__init__(
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
            name: str | None,
            srcs: StrOrListOpt,
            deps: StrOrListOpt,
            visibility: StrOrListOpt,
            tags: StrOrListOpt,
            resources: StrOrListOpt,
            source_encoding: str | None,
            warnings: str | None,
            exclusions: StrOrListOpt,
            kwargs: dict[str, object]):
        super().__init__(
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
            name: str | None,
            srcs: StrOrListOpt,
            deps: StrOrListOpt,
            visibility: StrOrListOpt,
            tags: StrOrListOpt,
            resources: StrOrListOpt,
            source_encoding: str | None,
            warnings: str | None,
            exclusions: StrOrListOpt,
            testdata: StrOrListOpt,
            kwargs: dict[str, object]):
        super().__init__(
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

        self._apply_scalatest_libs_from_config()

    def _apply_scalatest_libs_from_config(self):
        """Auto-inject the ScalaTest runtime declared by the workspace's
        ``scala_test_config(scalatest_libs=[...])``.

        Symmetric to ``JavaTest._apply_junit_libs_from_config`` in
        ``java_targets.py``; the two hooks exist for the same reason
        (turn a well-known config key into real implicit-deps
        injection so BUILD files don't have to repeat the runtime
        dep on every test target) and share the same three-branch
        contract:

        * ``scalatest_libs`` non-empty → forward the list as a whole
          to ``Target._add_implicit_library``, which handles label
          unification and dedup against the target's own ``deps``.
        * ``scalatest_libs`` is ``[]`` or missing (``None``) → emit
          one target-attributed warning pointing at the config key,
          and make no implicit-library call. Workspaces that prefer
          per-target explicit ``deps`` keep working, and users see
          an actionable message for the misconfiguration case.

        Kept as its own method, rather than inlined into ``__init__``,
        so unit tests can cover all three branches without having to
        construct a full ``ScalaTest`` instance against the build
        manager, and so a future ``gtest_libs`` / similar helper has
        an obvious template to copy.
        """
        scalatest_libs = config.get_item('scala_test_config', 'scalatest_libs')
        if scalatest_libs:
            self._add_implicit_library(scalatest_libs)
        else:
            self.warning(
                'Config: "scala_test_config.scalatest_libs" is not configured; '
                'scala_test targets must list their ScalaTest runtime in `deps` '
                'explicitly. See `blade dump --config` for the current value.'
            )

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


def scala_library(name: str,
                  srcs: StrOrListOpt = None,
                  deps: StrOrListOpt = None,
                  resources: StrOrListOpt = None,
                  visibility: StrOrListOpt = None,
                  tags: StrOrListOpt = None,
                  source_encoding: str | None = None,
                  warnings: str | None = None,
                  exported_deps: StrOrListOpt = None,
                  provided_deps: StrOrListOpt = None,
                  coverage: bool = True,
                  **kwargs: object):
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


def scala_fat_library(name: str,
                      srcs: StrOrListOpt = None,
                      deps: StrOrListOpt = None,
                      resources: StrOrListOpt = None,
                      visibility: StrOrListOpt = None,
                      tags: StrOrListOpt = None,
                      source_encoding: str | None = None,
                      warnings: str | None = None,
                      exclusions: StrOrListOpt = None,
                      **kwargs: object):
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


def scala_test(name: str,
               srcs: StrOrListOpt = None,
               deps: StrOrListOpt = None,
               resources: StrOrListOpt = None,
               visibility: StrOrListOpt = None,
               tags: StrOrListOpt = None,
               source_encoding: str | None = None,
               warnings: str | None = None,
               exclusions: StrOrListOpt = None,
               testdata: StrOrListOpt = None,
               **kwargs: object):
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
