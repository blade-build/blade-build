# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <phongchen@tencent.com>
# Created: Jun 26, 2013

# pylint: disable=too-many-lines

"""
Implement java_library, java_binary, java_test and java_fat_library.
"""

from __future__ import absolute_import
from __future__ import print_function

import collections
import os
import re

from blade import build_manager
from blade import build_rules
from blade import config
from blade import maven
from blade.target import Target, LOCATION_RE
from blade.util import var_to_list
from blade.util import iteritems
from blade.version import LooseVersion


class MavenJar(Target):
    """Describe a maven jar"""

    def __init__(self, name, id, classifier, transitive, visibility, tags):
        super(MavenJar, self).__init__(
                name=name,
                type='maven_jar',
                srcs=[],
                src_exts=None,
                deps=[],
                visibility=visibility,
                tags=tags,
                kwargs={})
        self._check_id(id)
        self._check_allowed_dirs()
        self.attr['id'] = id
        self.attr['classifier'] = classifier
        self.attr['transitive'] = transitive
        self._add_tags('lang:java', 'type:maven')
        self._setup()

    def _check_id(self, id):
        """Check if id is valid."""
        if id is None:
            self.error('Missing "id"')
        if not maven.is_valid_id(id):
            self.error('Invalid id %s: Id should be group:artifact:version, '
                       'such as jaxen:jaxen:1.1.6' % id)

    def _check_allowed_dirs(self):
        """Check whether the use of maven_jar is in allowed dirs"""
        allowed_dirs = config.get_item('java_config', 'maven_jar_allowed_dirs')
        if not allowed_dirs:
            return
        path = self.path
        while True:
            if path in allowed_dirs:
                return
            dirname = os.path.dirname(path)
            if dirname == path:
                break
            path = dirname

        msg = 'maven_jar is only allowed under %s and their subdirectories' % list(allowed_dirs)
        if self.key in config.get_item('java_config', 'maven_jar_allowed_dirs_exempts'):
            self.debug(msg)
        else:
            self.error(msg)

    def _get_java_pack_deps(self):
        return [], self.attr.get('maven_deps', [])

    def _setup(self):
        maven_cache = maven.MavenCache.instance(self.build_dir)
        maven_cache.schedule_download(self.attr['id'], self.attr['classifier'],
                                      self.attr['transitive'], self)

    def generate(self):
        # This muthod doesn't generate build code, so it is always executed without caching.
        if not self.dependents:  # Only download really used artifacts
            return
        maven_cache = maven.MavenCache.instance(self.build_dir)
        artifact = maven_cache.get_artifact(self.attr['id'], self.attr['classifier'],
                                            self.attr['transitive'], self)
        if artifact:
            self.attr['binary_jar'] = artifact.path
            self.attr['maven_deps'] = artifact.deps.split(':')


def debug_info_options():
    """javac debug information options(-g)"""
    global_config = config.get_section('global_config')
    java_config = config.get_section('java_config')
    debug_info_level = global_config['debug_info_level']
    return java_config['debug_info_levels'][debug_info_level]


_JAVA_SRC_PATH_SEGMENTS = (
    'src/main/java',
    'src/test/java',
    'src/java/',
)


class JavaTargetMixIn(object):
    """
    This mixin includes common java methods
    """

    def _expand_deps_java_generation(self):
        """Ensure that all multilingual dependencies such as proto_library generate java code."""
        queue = collections.deque(self.deps)
        keys = set()
        while queue:
            k = queue.popleft()
            if k not in keys:
                keys.add(k)
                dep = self.target_database[k]
                if 'generate_java' in dep.attr:  # Has this attribute
                    dep.attr['generate_java'] = True
                    if hasattr(dep, 'update_java_gen_info'):
                        dep.update_java_gen_info()
                    queue.extend(dep.deps)

    def _get_maven_dep_ids(self):
        maven_dep_ids = set()
        for dkey in self.deps:
            dep = self.target_database[dkey]
            if dep.type == 'maven_jar':
                id = dep.attr.get('id')
                if id:
                    maven_dep_ids.add(id)
        return maven_dep_ids

    def _unify_deps(self, deps):
        dkeys = []
        for dep in deps:
            dkey = self._unify_dep(dep)
            dkeys.append(dkey)
        return dkeys

    def __is_valid_maven_id_with_wildcards(self, id):
        wildcard = False
        for part in id.split(':'):
            if wildcard and part != '*':
                return False
            if part == '*':
                wildcard = True
        return True

    def _set_pack_exclusions(self, exclusions):
        exclusions = var_to_list(exclusions)
        self.attr['exclusions'] = []
        for exclusion in exclusions:
            if maven.is_valid_id(exclusion):
                if '*' in exclusion:
                    if not self.__is_valid_maven_id_with_wildcards(exclusion):
                        self.warning('Invalid maven id with wildcards %s. Ignored. The valid id '
                                     'could be: group:artifact:*, group:*:*, *:*:*' % exclusion)
                        continue
                self.attr['exclusions'].append(exclusion)
            else:
                self.warning('Exclusions only support maven id group:artifact:version. Ignore %s' %
                             exclusion)

    def _process_pack_exclusions(self, jars):
        """Exclude jars specified by exclusions from input jars."""
        exclusions = self.attr.get('exclusions', [])
        if exclusions:
            jars = set(jars)
            jars_excluded = set()
            for exclusion in exclusions:
                group, artifact, version = exclusion.split(':')
                group = group.replace('.', '/')
                jar_path = '.m2/repository'
                for part in (group, artifact, version):
                    if part == '*':
                        break
                    jar_path = os.path.join(jar_path, part)
                for jar in jars:
                    if jar_path in jar:
                        jars_excluded.add(jar)

            jars -= jars_excluded

        return jars

    def _process_resources(self, resources):
        """
        Process resources which could be regular files/directories or
        location references.
        """
        self.attr['resources'], self.attr['location_resources'] = [], []
        for resource in resources:
            if isinstance(resource, tuple):
                src, dst = resource
            elif isinstance(resource, str):
                src, dst = resource, ''
            else:
                self.error('Invalid resource %s. Resource should be either a str or a tuple.' %
                           resource)
                continue

            m = LOCATION_RE.search(src)
            if m:
                key, type = self._add_location_reference_target(m)
                self.attr['location_resources'].append((key, type, dst))
            else:
                self.attr['resources'].append((src, dst))

    def _get_classes_dir(self):
        """Return path of classes dir."""
        return self._target_file_path(self.name + '.classes')

    def _get_sources_dir(self):
        """Return path of sources dir."""
        return self._target_file_path(self.name + '.sources')

    def __collect_dep_jars(self, dkey, dep_jars, maven_jars):
        """Extract jar file built by the target with the specified dkey.

        dep_jars: a list of jars built by blade targets. Each item is a file path.
        maven_jars: a list of jars managed by maven repository.
        """
        dep = self.target_database[dkey]
        jar = dep._get_target_file('jar')
        if jar:
            dep_jars.append(jar)
        else:
            jar = dep.attr.get('binary_jar')
            if jar:
                assert dep.type == 'maven_jar'
                maven_jars.append(jar)

    def __get_dep_jars(self, deps):
        """Return a tuple of (target jars, maven jars)."""
        dep_jars, maven_jars = [], []
        for d in deps:
            self.__collect_dep_jars(d, dep_jars, maven_jars)
        return dep_jars, maven_jars

    def __get_exported_deps(self):
        """
        Recursively get exported dependencies and return a tuple of (target jars, maven jars)
        """
        dep_jars, maven_jars = [], []
        queue = collections.deque(self.deps)
        keys = set()
        while queue:
            key = queue.popleft()
            if key not in keys:
                keys.add(key)
                dep = self.target_database[key]
                exported_deps = dep.attr.get('exported_deps', [])
                for edkey in exported_deps:
                    self.__collect_dep_jars(edkey, dep_jars, maven_jars)
                queue.extend(exported_deps)

        return list(set(dep_jars)), list(set(maven_jars))

    def __get_maven_transitive_deps(self, deps):
        """
        Return a list of maven jars stored within local repository.
        These jars are transitive dependencies of maven_jar target.
        """
        maven_jars = []
        for key in deps:
            dep = self.target_database[key]
            if dep.type == 'maven_jar':
                maven_jars += dep.attr.get('maven_deps', [])
        return maven_jars

    def _detect_maven_conflicted_deps(self, scope, dep_jars):
        """
        Maven dependencies might have conflict: same group and artifact
        but different version. Select higher version by default unless
        a specific version of maven dependency is specified as a direct
        dependency of the target
        """
        # pylint: disable=too-many-locals
        maven_jar_versions = {}  # (group, artifact) -> versions
        maven_jars = {}  # (group, artifact, version) -> jars
        maven_repo = '.m2/repository/'
        for jar in set(dep_jars):
            if maven_repo not in jar or not os.path.exists(jar):
                self.debug('%s not found in local maven repository' % jar)
                continue
            parts = jar[jar.find(maven_repo) + len(maven_repo):].split('/')
            if len(parts) < 4:
                continue
            version, artifact, group = parts[-2], parts[-3], '.'.join(parts[:-3])
            key = group, artifact
            if key in maven_jar_versions:
                if version not in maven_jar_versions[key]:
                    maven_jar_versions[key].append(version)
            else:
                maven_jar_versions[key] = [version]
            key = group, artifact, version
            if key in maven_jars:
                maven_jars[key].append(jar)
            else:
                maven_jars[key] = [jar]

        maven_dep_ids = self._get_maven_dep_ids()
        jars = []
        for (group, artifact), versions in iteritems(maven_jar_versions):
            if len(versions) == 1:
                picked_version = versions[0]
            else:
                picked_version = None
                for v in versions:
                    maven_id = ':'.join((group, artifact, v))
                    if maven_id in maven_dep_ids:
                        picked_version = v
                        break
                    if picked_version is None or LooseVersion(v) > LooseVersion(picked_version):
                        picked_version = v
                self.debug('Maven dependency version conflict %s:%s:{%s} during %s. Use %s' % (
                    group, artifact, ', '.join(versions), scope, picked_version))
            jars += maven_jars[group, artifact, picked_version]
        return sorted(jars)

    def _get_compile_deps(self):
        dep_jars, maven_jars = self.__get_dep_jars(self.deps)
        exported_dep_jars, exported_maven_jars = self.__get_exported_deps()
        maven_jars += self.__get_maven_transitive_deps(self.deps)
        dep_jars = sorted(set(dep_jars + exported_dep_jars))
        maven_jars = self._detect_maven_conflicted_deps('compile',
                                                        maven_jars + exported_maven_jars)
        return dep_jars, maven_jars

    def _get_test_deps(self):
        dep_jars, maven_jars = self.__get_dep_jars(self.expanded_deps)
        maven_jars += self.__get_maven_transitive_deps(self.expanded_deps)
        dep_jars = sorted(set(dep_jars))
        maven_jars = self._process_pack_exclusions(maven_jars)
        maven_jars = self._detect_maven_conflicted_deps('test', maven_jars)
        return dep_jars, maven_jars

    def _get_pack_deps(self):
        """
        Recursively scan direct dependencies and exclude provided dependencies.
        """
        if 'java_pack_deps' in self.data:  # Cache result
            return self.data['java_pack_deps']

        deps = set(self.deps) - set(self.attr.get('provided_deps', []))
        dep_jars, maven_jars = self.__get_dep_jars(deps)

        for dep in deps:
            dep = self.target_database[dep]
            pack_dep_jars, pack_maven_jars = dep._get_java_pack_deps()
            dep_jars += pack_dep_jars
            maven_jars += pack_maven_jars

        dep_jars = sorted(set(dep_jars))
        maven_jars = sorted(self._process_pack_exclusions(set(maven_jars)))
        self.data['java_pack_deps'] = (dep_jars, maven_jars)
        return dep_jars, maven_jars

    def get_java_package_source_mapping(self):
        """
        Get java package_name/sourcefiles mapping
        """
        if not self.srcs:
            return {}
        # A dict of package : [source_path]
        key = 'java_package_source_mapping'
        if key in self.attr:
            return self.attr[key]
        mapping = collections.defaultdict(list)
        for src in self.srcs:
            src = self._source_file_path(src)
            package = self._get_source_package_name(src)
            if package:
                mapping[package].append(src)
        self.attr[key] = mapping
        return mapping

    def _get_java_package_names(self):
        """
        Get java package names. Usually all the sources are within the same package.
        However, there are cases where BUILD is in the parent directory and sources
        are located in subdirectories each of which defines its own package.
        """
        return self.get_java_package_source_mapping().keys()

    def _get_source_package_name(self, file_name):
        """Get the java package name from source file if it is specified."""
        if not os.path.isfile(file_name):
            return ''
        package_pattern = r'^\s*package\s+([\w.]+)'
        content = open(file_name).read()
        m = re.search(package_pattern, content, re.MULTILINE)
        if m:
            return m.group(1)

        return ''

    def _get_resource_path(self, resource):
        """
        Given a resource return its full path within the workspace
        and mapping path in the jar.
        """
        full_path, res_path, jar_path = '', resource[0], resource[1]
        if '..' in res_path:
            self.error('Invalid resource %s. Relative path is not allowed.' % res_path)
        elif res_path.startswith('//'):
            res_path = res_path[2:]
            full_path = res_path
            if not jar_path:
                jar_path = res_path
        else:
            full_path = self._source_file_path(res_path)
            if not jar_path:
                # Mapping rules from maven standard layout
                jar_path = self._java_resource_jar_path(res_path)
        return full_path, jar_path

    def _process_regular_resources(self, resources):
        results = set()
        for resource in resources:
            full_path, jar_path = self._get_resource_path(resource)
            if not os.path.exists(full_path):
                self.warning('Resource %s does not exist.' % full_path)
                results.add((full_path, jar_path))  # delay error to build phase
            elif os.path.isfile(full_path):
                results.add((full_path, jar_path))
            else:
                for dir, subdirs, files in os.walk(full_path):
                    # Skip over subdirs starting with '.', such as .svn
                    subdirs[:] = [d for d in subdirs if not d.startswith('.')]
                    for f in files:
                        f = os.path.join(dir, f)
                        rel_path = os.path.relpath(f, full_path)
                        results.add((f, os.path.join(jar_path, rel_path)))

        return sorted(results)

    def _java_sources_paths(self, srcs):
        path = set()
        for src in srcs:
            for seg in _JAVA_SRC_PATH_SEGMENTS:
                pos = src.find(seg)
                if pos > 0:
                    path.add(src[:pos + len(seg)])
                    continue
            package = self._get_source_package_name(src)
            if package:
                package = package.replace('.', '/') + '/'
                pos = src.find(package)
                if pos > 0:
                    path.add(src[:pos])
                    continue

        return list(path)

    def _java_resource_jar_path(self, resource):
        """ Calculate in jar path for a resource path.

        Resource path mapping rules from local directory to jar entry. See
        https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html
        for maven rules.
        """
        segs = [
            'src/main/resources',
            'src/test/resources',
            'resources',
        ]
        for seg in segs:
            pos = resource.find(seg)
            if pos == -1:
                continue
            if pos > 0 and resource[pos - 1] != '/':
                continue
            end = pos + len(seg)
            if end < len(resource) and resource[end] != '/':
                continue
            # skip the separator '/', if resource ends with '/', "+ 1" is still ok in python
            jar_path = resource[end + 1:]
            return jar_path
        return resource

    def _packages_under_test(self):
        """Package names under test"""
        packages = []
        for dkey in self.deps:
            dep = self.target_database[dkey]
            if not dep.attr.get('jacoco_coverage'):
                continue
            packages += dep._get_java_package_names()
        return ':'.join(packages)

    def _generate_sources_dir_for_coverage(self):
        """
        Generate a '<name>.sources' dir in the build directory for the subsequent
        code coverage. The layout is based on the package parsed from sources.
        Note that the classes are still compiled from the sources in the
        source directory.
        """
        sources_dir = self._get_sources_dir()
        self._remove_on_clean(sources_dir)

        if not getattr(self.blade.get_options(), 'coverage', False):
            return

        for source in self.srcs:
            src = self._source_file_path(source)
            if not os.path.exists(src):  # Maybe it's a generated file
                continue
            package = self._get_source_package_name(src)
            dst = os.path.join(sources_dir, package.replace('.', '/'),
                               os.path.basename(source))
            self.generate_build('copy', dst, inputs=src)

    def _generate_resources(self):
        resources = self.attr['resources']
        locations = self.attr['location_resources']
        if not resources and not locations:
            return []
        inputs, outputs = [], []
        resources_dir = self._target_file_path(self.name + '.resources')
        resources = self._process_regular_resources(resources)
        for src, dst in resources:
            inputs.append(src)
            outputs.append(os.path.join(resources_dir, dst))
        targets = self.blade.get_build_targets()
        for key, type, dst in locations:
            path = targets[key]._get_target_file(type)
            if not path:
                self.warning('Location %s %s is missing. Ignored.' % (key, type))
                continue
            if not dst:
                dst = os.path.basename(path)
            inputs.append(path)
            outputs.append(os.path.join(resources_dir, dst))
        if inputs:
            self.generate_build('javaresource', outputs, inputs=inputs,
                                variables={'resources_dir': resources_dir})
            self._remove_on_clean(resources_dir)
        return outputs

    def _generate_fat_jar(self):
        self._generate_jar()
        dep_jars, maven_jars = self._get_pack_deps()
        maven_jars = self._detect_maven_conflicted_deps('package', maven_jars)
        return self._build_fat_jar(dep_jars, maven_jars)

    def _java_implicit_dependencies(self, dep_jars, maven_jars):
        return dep_jars + [jar for jar in maven_jars if '-SNAPSHOT' in jar]

    def _build_jar(self, output=None, inputs=None,
                   source_encoding=None, javacflags=None,
                   scala=False, scalacflags=None):
        if not output:
            output = self._target_file_path(self.name + '.jar')
        if not inputs:
            inputs = [self._source_file_path(s) for s in self.srcs]
        if scala:
            rule = 'scalac'
            vars = {}
            if scalacflags:
                vars['scalacflags'] = ' '.join(scalacflags)
        else:
            rule = 'javac'
            classes_dir = self._get_classes_dir()
            self._remove_on_clean(classes_dir)
            vars = {'classes_dir': classes_dir}
            if javacflags:
                vars['javacflags'] = ' '.join(javacflags)
        dep_jars, maven_jars = self._get_compile_deps()
        implicit_deps = self._java_implicit_dependencies(dep_jars, maven_jars)
        jars = dep_jars + maven_jars
        if jars:
            vars['classpath'] = ':'.join(jars)
        if source_encoding:
            vars['source_encoding'] = source_encoding
        self.generate_build(rule, output, inputs=inputs,
                            implicit_deps=implicit_deps, variables=vars)
        return output

    def _build_fat_jar(self, dep_jars, maven_jars):
        jar = self._get_target_file('jar')
        if jar:
            inputs = [jar]
        else:
            inputs = []
        inputs += dep_jars + maven_jars
        output = self._target_file_path(self.name + '.fat.jar')
        log = self._target_file_path(self.name + '__fatjar__.log')
        self.generate_build('fatjar', output, implicit_outputs=log, inputs=inputs)
        return output


class JavaTarget(Target, JavaTargetMixIn):
    """A java jar target subclass.

    This class is the base of all java targets.

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

        Init the java jar target.

        """
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        resources = var_to_list(resources)

        super(JavaTarget, self).__init__(
                name=name,
                type=type,
                srcs=srcs,
                src_exts=['java'],
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)
        self._process_resources(resources)
        self.attr['source_encoding'] = source_encoding
        self._add_tags('lang:java')

        if warnings is not None:
            self.attr['warnings'] = var_to_list(warnings)

    def _expand_deps_generation(self):
        self._expand_deps_java_generation()

    def _get_java_pack_deps(self):
        return self._get_pack_deps()

    def javac_flags(self):
        warnings = self.attr.get('warnings')
        if not warnings:
            warnings = config.get_item('java_config', 'warnings')
        return debug_info_options() + warnings

    def _java_full_path_srcs(self):
        """Expand srcs to full path"""
        srcs = []
        for s in self.srcs:
            sp = self._source_file_path(s)
            # If it doesn't exist, consider it as a generated file in target dir
            srcs.append(sp if os.path.exists(sp) else self._target_file_path(s))
        return srcs

    def _generate_jar(self):
        self._generate_sources_dir_for_coverage()
        srcs = self._java_full_path_srcs()
        resources = self._generate_resources()
        jar = self._target_file_path(self.name + '.jar')
        if srcs and resources:
            classes_jar = self._target_file_path(self.name + '__classes__.jar')
            javacflags = self.javac_flags()
            self._build_jar(classes_jar, inputs=srcs, javacflags=javacflags)
            self.generate_build('javajar', jar, inputs=[classes_jar] + resources)
        elif srcs:
            javacflags = self.javac_flags()
            self._build_jar(jar, inputs=srcs, javacflags=javacflags)
        elif resources:
            self.generate_build('javajar', jar, inputs=resources)
        else:
            jar = ''
        if jar:
            self._add_target_file('jar', jar)
        return jar


class JavaLibrary(JavaTarget):
    """JavaLibrary"""

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
            prebuilt,
            binary_jar,
            exported_deps,
            provided_deps,
            coverage,
            kwargs):
        type = 'java_library'
        if prebuilt:
            type = 'prebuilt_java_library'
        exported_deps = var_to_list(exported_deps)
        provided_deps = var_to_list(provided_deps)
        all_deps = var_to_list(deps) + exported_deps + provided_deps
        super(JavaLibrary, self).__init__(
                name=name,
                type=type,
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
        self._add_tags('type:library')
        if prebuilt:
            if not binary_jar:
                binary_jar = name + '.jar'
            self.attr['binary_jar'] = self._source_file_path(binary_jar)
            self._add_tags('type:prebuilt')
        self.attr['jacoco_coverage'] = coverage and bool(srcs)

    def generate(self):
        if self.type == 'prebuilt_java_library':
            jar = os.path.join(self.blade.get_root_dir(),
                               self.attr['binary_jar'])
        else:
            jar = self._generate_jar()
        if jar:
            self._add_default_target_file('jar', jar)


class JavaBinary(JavaTarget):
    """JavaBinary"""

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
            main_class,
            exclusions,
            kwargs):
        super(JavaBinary, self).__init__(
                name=name,
                type='java_binary',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                resources=resources,
                source_encoding=source_encoding,
                warnings=warnings,
                kwargs=kwargs)
        self.attr['main_class'] = main_class
        self.attr['run_in_shell'] = True
        self._add_tags('type:binary')
        if not main_class:
            self.warning('Missing "main_class", program may not run')
        if exclusions:
            self._set_pack_exclusions(exclusions)

    def _generate_one_jar(self, dep_jars, maven_jars):
        jar = self._get_target_file('jar')
        if jar:
            inputs = [jar]
        else:
            inputs = []
        inputs += dep_jars + maven_jars
        output = self._target_file_path(self.name + '.one.jar')
        vars = {'mainclass': self.attr['main_class']}
        self.generate_build('onejar', output, inputs=inputs, variables=vars)
        self._add_target_file('onejar', output)
        return output

    def generate(self):
        self._generate_jar()
        dep_jars, maven_jars = self._get_pack_deps()
        maven_jars = self._detect_maven_conflicted_deps('package', maven_jars)
        onejar = self._generate_one_jar(dep_jars, maven_jars)
        output = self._target_file_path(self.name)
        self.generate_build('javabinary', output, inputs=onejar)
        self._add_default_target_file('bin', output)


class JavaFatLibrary(JavaTarget):
    """JavaFatLibrary"""

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
        super(JavaFatLibrary, self).__init__(
                name=name,
                type='java_fat_library',
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                resources=resources,
                source_encoding=source_encoding,
                warnings=warnings,
                kwargs=kwargs)
        self._add_tags('type:library', 'type:fatjar')
        if exclusions:
            self._set_pack_exclusions(exclusions)

    def generate(self):
        jar = self._generate_fat_jar()
        self._add_default_target_file('fatjar', jar)


class JavaTest(JavaBinary):
    """JavaTest"""

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
            main_class,
            exclusions,
            testdata,
            target_under_test,
            kwargs):
        super(JavaTest, self).__init__(
                name=name,
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                resources=resources,
                source_encoding=source_encoding,
                warnings=warnings,
                main_class=main_class,
                exclusions=exclusions,
                kwargs=kwargs)
        if target_under_test:
            self.warning('"target_under_test" is deprecated, you can remove it safely')
        self.type = 'java_test'
        self.attr['testdata'] = var_to_list(testdata)
        self._add_tags('type:test')

    def _java_test_vars(self):
        vars = {
            'mainclass': self.attr['main_class'],
            'packages_under_test': self._packages_under_test()
        }
        return vars

    def generate(self):
        if not self.srcs:
            self.warning('Empty java test sources')
            return
        vars = self._java_test_vars()
        jar = self._generate_jar()
        output = self._target_file_path(self.name)
        dep_jars, maven_jars = self._get_test_deps()
        self.generate_build('javatest', output, inputs=[jar] + dep_jars + maven_jars, variables=vars)


def maven_jar(name=None, id=None, classifier='', transitive=True, visibility=None, tags=[]):
    target = MavenJar(name, id, classifier, transitive, visibility, tags)
    build_manager.instance.register_target(target)


def java_library(name=None,
                 srcs=[],
                 deps=[],
                 visibility=None,
                 tags=[],
                 resources=[],
                 source_encoding=None,
                 warnings=None,
                 prebuilt=False,
                 binary_jar='',
                 exported_deps=[],
                 provided_deps=[],
                 coverage=True,
                 **kwargs):
    """Define java_library target.

    Args:
        coverage: bool, Whether generate test coverage data for this library.
            It is useful to be False in some cases such as srcs are generated.
    """
    target = JavaLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            resources=resources,
            source_encoding=source_encoding,
            warnings=warnings,
            prebuilt=prebuilt,
            binary_jar=binary_jar,
            exported_deps=exported_deps,
            provided_deps=provided_deps,
            coverage=coverage,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


def java_binary(name=None,
                main_class='',
                srcs=[],
                deps=[],
                visibility=None,
                tags=[],
                resources=[],
                source_encoding=None,
                warnings=None,
                exclusions=[],
                **kwargs):
    """Define java_binary target."""
    target = JavaBinary(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            resources=resources,
            source_encoding=source_encoding,
            warnings=warnings,
            main_class=main_class,
            exclusions=exclusions,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


def java_test(name=None,
              srcs=None,
              deps=[],
              visibility=None,
              tags=[],
              resources=[],
              source_encoding=None,
              warnings=None,
              main_class='org.junit.runner.JUnitCore',
              exclusions=[],
              testdata=[],
              target_under_test=None,
              **kwargs):
    """Build a java test target"""
    target = JavaTest(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            resources=resources,
            source_encoding=source_encoding,
            warnings=warnings,
            main_class=main_class,
            exclusions=exclusions,
            testdata=testdata,
            target_under_test=target_under_test,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


def java_fat_library(name=None,
                     srcs=[],
                     deps=[],
                     visibility=None,
                     tags=[],
                     resources=[],
                     source_encoding=None,
                     warnings=None,
                     exclusions=[],
                     **kwargs):
    """Define java_fat_library target."""
    target = JavaFatLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            resources=resources,
            source_encoding=source_encoding,
            warnings=warnings,
            exclusions=exclusions,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(maven_jar)
build_rules.register_function(java_binary)
build_rules.register_function(java_library)
build_rules.register_function(java_test)
build_rules.register_function(java_fat_library)
