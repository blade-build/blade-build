# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
This is the blade module which mainly holds the global database and
do the coordination work between classes.
"""

from __future__ import absolute_import
from __future__ import print_function

import json
import os
import subprocess
import sys
import time

from blade import config
from blade import console
from blade import maven
from blade import ninja_runner
from blade import target_pattern
from blade import toolchain
from blade.binary_runner import BinaryRunner
from blade.build_accelerator import BuildAccelerator
from blade.dependency_analyzer import analyze_deps
from blade.load_build_files import load_targets
from blade.backend import NinjaFileGenerator
from blade.test_runner import TestRunner
from blade.util import (cpu_count, md5sum_file, pickle)

# Global build manager instance
instance = None


# Start of fingerprint line in each per-target ninja file
_NINJA_FILE_FINGERPRINT_START = '#Fingerprint='

_ALL_COMMAND_TARGETS = '__ALL_COMMAND_TARGETS__'

class Blade(object):
    """Blade. A blade manager class."""

    # pylint: disable=too-many-public-methods
    def __init__(self,
                 blade_path,
                 command,
                 options,
                 workspace,
                 targets):
        """init method.

        Args:
            command_targets: List[str], target patterns are specified in command line.
            load_targets: List[str], target patterns should be loaded from workspace. It usually should be same
                as the command_targets, but in query dependents mode, all targets should be loaded.
            blade_path: str, the path of the `blade` python module, used to be called by builtin tools.
        """
        self.__command_targets = targets
        # In query dependents mode, we must load all targets in workspace to get a whole view
        self.__load_targets = ['.:...'] if command == 'query' and options.dependents else targets
        self.__blade_path = blade_path
        self.__root_dir = workspace.root_dir()
        self.__build_dir = workspace.build_dir()
        self.__working_dir = workspace.working_dir()

        self.__options = options
        self.__command = command

        # Source dir of current loading BUILD file
        self.__current_source_path = ''

        self.__blade_revision = None

        # The targets which are specified in command line explicitly, not the pattern expanded.
        self.__direct_targets = set()

        # All command targets, includes direct targets and expanded target patterns.
        self.__expanded_command_targets = set()

        # Given some targets specified in the command line, Blade will load
        # BUILD files containing these command line targets; global target
        # functions, i.e., cc_library, cc_binary and etc, in these BUILD
        # files will register targets into target_database, which then becomes
        # the input to dependency analyzer and backend build code generator.  It is
        # notable that not all targets in target_database are dependencies of
        # command line targets.
        self.__target_database = {}

        # The targets to be build after loading the build files.
        self.__build_targets = {}

        # The targets keys list after sorting by topological sorting method.
        # Used to generate build code in correct order.
        self.__sorted_targets_keys = []

        # Indicate whether the deps list is expanded by expander or not
        self.__targets_expanded = False

        self.__cc_toolchain = toolchain.default(options.m)
        self.build_accelerator = BuildAccelerator(self.__cc_toolchain)
        self.__build_jobs_num = 0

        self.__build_script = os.path.join(self.__build_dir, 'build.ninja')

        self.__all_rule_names = []

    def load_targets(self):
        """Load the targets."""
        console.info('Loading BUILD files...')
        excluded_targets = target_pattern.normalize_str_list(self.__options.exclude_targets,
                                                             self.__working_dir, ',')
        (self.__direct_targets,
         self.__expanded_command_targets,
         self.__build_targets) = load_targets(self.__load_targets, excluded_targets, self)
        if self.__command_targets != self.__load_targets:
            # In query dependents mode, we must use command targets to execute query
            self.__expanded_command_targets = self._expand_command_targets()
        console.info('Loading done.')
        return self.__direct_targets, self.__expanded_command_targets  # For test

    def _expand_command_targets(self):
        """Expand command line targets to targets list"""
        all_command_targets = []
        for tkey in self.__build_targets:
            for pattern in self.__command_targets:
                if target_pattern.match(tkey, pattern):
                    all_command_targets.append(tkey)
        return all_command_targets

    def analyze_targets(self):
        """Expand the targets."""
        console.info('Analyzing dependency graph...')
        self.__sorted_targets_keys = analyze_deps(self.__build_targets)
        self.__targets_expanded = True

        console.info('Analyzing done.')
        return self.__build_targets  # For test

    def build_script(self):
        """Return build script file name"""
        return self.__build_script

    def generate_build_code(self):
        """Generate the backend build code."""
        console.info('Generating backend build code...')
        generator = NinjaFileGenerator(self.__build_script, self.__blade_path, self)
        generator.generate_build_script()
        self.__all_rule_names = generator.get_all_rule_names()
        console.info('Generating done.')

    def generate(self):
        """Generate the build script."""
        if self.__command == 'query':
            return
        maven_cache = maven.MavenCache.instance(self.__build_dir)
        maven_cache.download_all()
        self._write_inclusion_declaration_file()
        self.generate_build_code()

    def _write_inclusion_declaration_file(self):
        from blade import cc_targets  # pylint: disable=import-outside-toplevel
        inclusion_declaration_file = os.path.join(self.__build_dir, 'inclusion_declaration.data')
        with open(inclusion_declaration_file, 'wb') as f:
            pickle.dump(cc_targets.inclusion_declaration(), f)

    def _write_build_stamp_fime(self, start_time, exit_code):
        """Record some useful data for other tools."""
        stamp_data = {
            'start_time': start_time,
            'end_time': time.time(),
            'exit_code': exit_code,
            'direct_targets': list(self.__direct_targets),
            'command_targets': list(self.__expanded_command_targets),
            'build_targets': list(self.__build_targets.keys()),
            'loaded_targets': list(self.__target_database.keys()),
        }
        stamp_file = os.path.join(self.__build_dir, 'blade_build_stamp.json')
        with open(stamp_file, 'w') as f:
            json.dump(stamp_data, f, indent=4)

    def revision(self):
        """Blade revision to identify changes"""
        if self.__blade_revision is None:
            if os.path.isfile(self.__blade_path):  # blade.zip
                self.__blade_revision = md5sum_file(self.__blade_path)
            else:
                # In develop mode, take the mtime of the `blade` directory
                self.__blade_revision = str(os.path.getmtime(
                    os.path.join(self.__blade_path, 'blade')))
        return self.__blade_revision

    def build(self):
        """Implement the "build" subcommand."""
        console.info('Building...')
        console.flush()
        start_time = time.time()
        returncode = ninja_runner.build(
            self.get_build_dir(),
            self.build_script(),
            self.build_jobs_num(),
            targets='',  # FIXME: because not all targets has a targets
            options=self.__options)
        self._write_build_stamp_fime(start_time, returncode)
        if returncode != 0:
            console.error('Build failure.')
        else:
            console.info('Build success.')
        return returncode

    def run(self):
        """Build and run target"""
        ret = self.build()
        if ret != 0:
            return ret
        return self._run()

    def _run(self):
        """Run the target."""
        runner = BinaryRunner(self.__options, self.__target_database, self.__build_targets)
        return runner.run_target(list(self.__direct_targets)[0])

    def test(self):
        """Build and run tests."""
        if not self.__options.no_build:
            ret = self.build()
            if ret != 0:
                return ret
        return self._test()

    def _test(self):
        """Run tests."""
        exclude_tests = []
        if self.__options.exclude_tests:
            exclude_tests = target_pattern.normalize_str_list(self.__options.exclude_tests,
                                                              self.__working_dir, ',')
        test_runner = TestRunner(
                self.__options,
                self.__target_database,
                self.__direct_targets,
                self.__expanded_command_targets,
                self.__build_targets,
                exclude_tests,
                self.test_jobs_num())
        return test_runner.run()

    @staticmethod
    def _remove_paths(paths):
        # The rm command can delete a large number of files at once, which is much faster than
        # using python's own remove functions (only supports deleting a single path at a time).
        if os.name == 'posix':
            subprocess.call(['rm', '-fr'] + paths)
            return
        import shutil
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)

    def clean(self):
        """Clean specific generated target files or directories"""
        console.info('Cleaning...')
        paths = []
        for key in self.__expanded_command_targets:
            target = self.__build_targets[key]
            clean_list = target.get_clean_list()
            console.debug('Cleaning %s: %s' % (target.fullname, clean_list))
            # Batch removing is much faster than one by one
            paths += clean_list
            if len(paths) > 10000:  # Avoid 'Argument list too long' error.
                self._remove_paths(paths)
                paths[:] = []
        if paths:
            self._remove_paths(paths)
        console.info('Cleaning done.')
        return 0

    def query(self):
        """Query the targets."""
        output_file_name = self.__options.output_file
        if output_file_name:
            output_file_name = os.path.join(self.__working_dir, output_file_name)
            output_file = open(output_file_name, 'w')
            console.info('Query result will be written to file "%s"' % self.__options.output_file)
        else:
            output_file = sys.stdout
            console.info('Query result:')

        output_format = self.__options.output_format
        if output_format == 'dot':
            self.query_dependency_dot(output_file)
        elif output_format == 'tree':
            self.query_dependency_tree(output_file)
        else:
            self.query_dependency_plain(output_file)
        if output_file_name:
            output_file.close()
        return 0

    def query_dependency_plain(self, output_file):
        all_targets = self.__build_targets
        query_list = self.__expanded_command_targets
        if self.__options.deps:
            for key in query_list:
                print(file=output_file)
                deps = all_targets[key].expanded_deps
                print('//%s depends on the following targets:' % key, file=output_file)
                for d in deps:
                    print('%s' % d, file=output_file)
        if self.__options.dependents:
            for key in query_list:
                print(file=output_file)
                depended_by = all_targets[key].expanded_dependents
                print('//%s is depended by the following targets:' % key, file=output_file)
                for d in depended_by:
                    print('%s' % d, file=output_file)

    def print_dot_node(self, output_file, node):
        print('"%s" [label = "%s"]' % (node, node), file=output_file)

    def print_dot_deps(self, output_file, node, target_set):
        targets = self.__build_targets
        deps = targets[node].deps
        for i in deps:
            if i not in target_set:
                continue
            print('"%s" -> "%s"' % (node, i), file=output_file)

    def __print_dot_graph(self, attr_name, output_file):
        # Collect all related nodes
        query_list = self.__expanded_command_targets
        nodes = set(query_list)
        for key in query_list:
            nodes |= set(getattr(self.__build_targets[key], 'expanded_' + attr_name))

        print('digraph %s {' % attr_name, file=output_file)
        for i in nodes:
            self.print_dot_node(output_file, i)
        for i in nodes:
            self.print_dot_deps(output_file, i, nodes)
        print('}', file=output_file)

    def query_dependency_dot(self, output_file):
        if self.__options.deps:
            self.__print_dot_graph('deps', output_file)
        if self.__options.dependents:
            self.__print_dot_graph('dependents', output_file)

    def query_dependency_tree(self, output_file):
        """Query the dependency tree of the specified targets."""
        path_to = self._parse_qyery_path_to()
        query_attr = 'dependents' if self.__options.dependents else 'deps'
        print(file=output_file)
        for key in self.__expanded_command_targets:
            self._query_dependency_tree(key, 0, query_attr, path_to, output_file)
            print(file=output_file)

    def _parse_qyery_path_to(self):
        """Parse the `--path-to` command line argument"""
        if not self.__options.query_path_to:
            return set()
        result = set()
        for id in target_pattern.normalize_list(
                self.__options.query_path_to.split(','),
                self.__working_dir):
            if id not in self.__target_database:
                console.fatal('Invalid argument: "--path-to=%s", target "%s" does not exist' % (
                        self.__options.query_path_to, id))
            result.add(id)
        return result

    def _query_dependency_tree(self, key, level, query_attr, path_to, output_file):
        """Query the dependency tree of the specified target recursively."""
        if level == 0:
            output = '%s' % key
        elif level == 1:
            output = '%s %s' % ('+-', key)
        else:
            output = '%s%s %s' % ('|  ' * (level - 1), '+-', key)
        print(output, file=output_file)
        for dkey in getattr(self.__build_targets[key], query_attr):
            if self._query_path_match(dkey, path_to):
                self._query_dependency_tree(dkey, level + 1, query_attr, path_to, output_file)

    def _query_path_match(self, dkey, path_to):
        """Test whether we can reach `path_to` from `dkey`"""
        if not path_to:
            return True
        if dkey in path_to:
            return True
        dep = self.__build_targets[dkey]
        if path_to & set(dep.expanded_deps):
            return True
        return False

    def dump(self):
        """Implement the "dump" subcommand."""
        working_dir = self.get_working_dir()
        output_file_name = os.path.join(working_dir, self.__options.dump_to_file)
        if self.__options.dump_compdb:
            return self._dump_compdb(output_file_name)
        if self.__options.dump_targets:
            return self._dump_targets(output_file_name)
        if self.__options.dump_all_tags:
            return self._dump_all_tags(output_file_name)
        # The "--config" is already handled before this
        raise AssertionError("Invalid dump option")

    def _dump_compdb(self, output_file_name):
        """Implement the "dump --compdb" subcommand."""
        return ninja_runner.dump_compdb(
            self.build_script(),
            self.get_all_rule_names(),
            output_file_name)

    def _dump_targets(self, output_file_name):
        """Implement the "dump --targets" subcommand."""
        result = []
        with open(output_file_name, 'w') as f:
            for target_key in self.__expanded_command_targets:
                target = self.__target_database[target_key]
                result.append(target.dump())
            json.dump(result, fp=f, indent=2, sort_keys=True)
            print(file=f)
        return 0

    def _dump_all_tags(self, output_file_name):
        """Implement the "dump --targets" subcommand."""
        with open(output_file_name, 'w') as f:
            all_tags = set()
            for key, target in self.__build_targets.items():
                all_tags.update(target.tags)
            json.dump(sorted(list(all_tags)), fp=f, indent=2)
            print(file=f)
        return 0

    def get_build_dir(self):
        """The current building dir."""
        return self.__build_dir

    def get_root_dir(self):
        """Return the blade root path."""
        return self.__root_dir

    def get_working_dir(self):
        """Return the working dir (in which user invoke blade)."""
        return self.__working_dir

    def get_command(self):
        """Get the blade command."""
        return self.__command

    def set_current_source_path(self, current_source_path):
        """Set the current source path."""
        if current_source_path == '.':
            # For the workspace root dir, we should normalize it to be empty,
            # otherwise other targets can't depend on it.
            current_source_path = ''
        self.__current_source_path = current_source_path

    def get_current_source_path(self):
        """Get the current source path."""
        return self.__current_source_path

    def get_target_database(self):
        """Get the whole target database that haven't been expanded."""
        return self.__target_database

    def get_direct_targets(self):
        """Return the direct targets."""
        return self.__direct_targets

    def get_build_targets(self):
        """Get all the targets to be build."""
        return self.__build_targets

    def get_options(self):
        """Get the global command options."""
        return self.__options

    def is_expanded(self):
        """Whether the targets are expanded."""
        return self.__targets_expanded

    def register_target(self, target):
        """Register a target into blade target database.
        It is used to do quick looking.
        """
        key = target.key
        # Check whether there is already a key in database
        if key in self.__target_database:
            console.fatal('Target %s is duplicate in //%s/BUILD' % (target.name, target.path))
        self.__target_database[key] = target

    def _read_fingerprint(self, ninja_file):
        """Read fingerprint from per-target ninja file"""
        try:
            with open(ninja_file, buffering=64) as f:
                first_line = f.readline()
                if first_line.startswith(_NINJA_FILE_FINGERPRINT_START):
                    return first_line[len(_NINJA_FILE_FINGERPRINT_START):].strip()
        except IOError:
            pass
        return None

    def _write_target_ninja_file(self, target, ninja_file, code, fingerprint):
        """Generate per-target ninja file"""
        target_dir = target._target_file_path('')
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
        with open(ninja_file, 'w') as f:
            f.write('%s%s\n\n' % (_NINJA_FILE_FINGERPRINT_START, fingerprint))
            f.writelines(code)

    def _find_or_generate_target_ninja_file(self, target):
        # The `.build.` infix is used to avoid the target ninja file with the
        # same name as the main build.ninja file (when target.name == 'build')
        target_ninja = target._target_file_path('%s.build.ninja' % target.name)

        old_fingerprint = self._read_fingerprint(target_ninja)
        fingerprint = target.fingerprint()

        if fingerprint == old_fingerprint:
            console.debug('Using cached %s' % target_ninja)
            # If the command is "clean", we still need to generate rules to obtain the clean list
            if self.__command == 'clean':
                target.get_build_code()
            return target_ninja

        code = target.get_build_code()
        if code:
            console.debug('Generating %s' % target_ninja)
            self._write_target_ninja_file(target, target_ninja, code, fingerprint)
            return target_ninja

        return None

    def generate_targets_build_code(self):
        """Generate backend build code for each build targets."""
        code = []
        skip_test = getattr(self.__options, 'no_test', False)
        skip_package = not getattr(self.__options, 'generate_package', False)
        command_target_outputs = []
        for k in self.__sorted_targets_keys:
            target = self.__build_targets[k]
            if skip_test and target.type.endswith('_test') and k not in self.__direct_targets:
                continue
            if skip_package and target.type == 'package' and k not in self.__direct_targets:
                continue
            target.before_generate()
            target_ninja = self._find_or_generate_target_ninja_file(target)
            if target_ninja:
                target._remove_on_clean(target_ninja)
                code += 'include %s\n' % target_ninja
                if k in self.__expanded_command_targets:
                    command_target_outputs.append(target.get_outputs_goal())
        # TODO: reland this feature
        # code.append('build %s: phony %s\n' % (_ALL_COMMAND_TARGETS, ' '.join(command_target_outputs)))
        # code.append('default %s\n' % (_ALL_COMMAND_TARGETS))
        return code

    def get_cc_toolchain(self):
        """Return cc build toolchain instance."""
        return self.__cc_toolchain

    def get_sources_keyword_list(self):
        """This keywords list is used to check the source files path.

        Ex, when users specifies warning=no, it could be used to check that
        the source files is under thirdparty or not. If not, it will warn
        users that this flag is used incorrectly.

        """
        keywords = ['thirdparty']
        return keywords

    def _build_jobs_num(self):
        """Calculate build jobs num."""
        # User has the highest priority
        jobs_num = config.get_item('global_config', 'build_jobs')
        if jobs_num > 0:
            return jobs_num
        jobs_num = self.build_accelerator.adjust_jobs_num(cpu_count())
        console.info('Adjust build jobs number(-j N) to be %d' % jobs_num)
        return jobs_num

    def build_jobs_num(self):
        """The number of build jobs"""
        if self.__build_jobs_num == 0:
            self.__build_jobs_num = self._build_jobs_num()
        return self.__build_jobs_num

    def test_jobs_num(self):
        """Calculate the number of test jobs"""
        # User has the highest priority
        jobs_num = config.get_item('global_config', 'test_jobs')
        if jobs_num > 0:
            return jobs_num
        # In distcc enabled mode, the build_jobs_num may be quiet large, but we
        # only support run test locally, so the test_jobs_num should be limited
        # by local cpu mumber.
        # WE limit the test_jobs_num to be half of build job number because test
        # may be heavier than build (may be not, perhaps).
        build_jobs_num = self.build_jobs_num()
        cpu_core_num = cpu_count()
        jobs_num = max(min(build_jobs_num, cpu_core_num) // 2, 1)
        console.info('Adjust test jobs number(-j N) to be %d' % jobs_num)
        return jobs_num

    def get_all_rule_names(self):
        return self.__all_rule_names


def initialize(blade_path, command, options, workspace, targets):
    global instance
    instance = Blade(blade_path, command, options, workspace, targets)
    return instance
