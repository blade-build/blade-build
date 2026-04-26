# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Authors: Huan Yu <huanyu@tencent.com>
#          Feng Chen <phongchen@tencent.com>
#          Yi Wang <yiwang@tencent.com>
#          Chong Peng <michaelpeng@tencent.com>
# Date: October 20, 2011


"""
This module executes a binary programs.
"""

from __future__ import absolute_import
from __future__ import print_function

import os
import shutil
import subprocess
import sys

from blade import config
from blade import console
from blade.util import environ_add_path


class BinaryRunner(object):
    """BinaryRunner."""

    def __init__(self, options, target_database, build_targets):
        """Init method."""
        from blade import build_manager  # pylint: disable=import-outside-toplevel
        self._build_targets = build_targets
        self.build_dir = build_manager.instance.get_build_dir()
        self.options = options
        self.run_list = ['cc_binary',
                         'cc_test',
                         'java_binary',
                         'java_test',
                         'py_binary',
                         'py_test',
                         'scala_test',
                         'sh_test']
        self.target_database = target_database

    def _executable(self, target):
        """Returns the executable path."""
        return os.path.join(self.build_dir, target.path, target.name)

    def _runfiles_dir(self, target):
        """Returns runfiles dir."""
        return '%s.runfiles' % self._executable(target)

    def __check_test_data_dest(self, target, dest, dest_list):
        """Check whether the destination of test data is valid or not."""
        dest_norm = os.path.normpath(dest)
        if dest in dest_list:
            target.error('Ambiguous testdata "%s"' % dest)
        for item in dest_list:
            item_norm = os.path.normpath(item)
            if len(dest_norm) >= len(item_norm):
                long_path, short_path = dest_norm, item_norm
            else:
                long_path, short_path = item_norm, dest_norm
            if long_path.startswith(short_path) and long_path[len(short_path)] == '/':
                target.error('"%s" could not exist with "%s" in testdata' % (dest, item))

    def _prepare_env(self, target):
        """Prepare the running environment."""

        # Prepare `<target_name>.runfiles` directory
        runfiles_dir = self._runfiles_dir(target)
        shutil.rmtree(runfiles_dir, ignore_errors=True)
        os.mkdir(runfiles_dir)

        self._prepare_shared_libraries(target, runfiles_dir)
        self._prepare_test_data(target)

        # Prepare environments
        run_env = dict(os.environ)
        environ_add_path(run_env, 'LD_LIBRARY_PATH', runfiles_dir)
        run_lib_paths = config.get_item('cc_binary_config', 'run_lib_paths')
        if run_lib_paths:
            for path in run_lib_paths:
                if path.startswith('//'):
                    path = path[2:]
                path = os.path.abspath(path)
                environ_add_path(run_env, 'LD_LIBRARY_PATH', path)
        java_home = config.get_item('java_config', 'java_home')
        if java_home:
            java_home = os.path.abspath(java_home)
            environ_add_path(run_env, 'PATH', os.path.join(java_home, 'bin'))

        return run_env

    def _prepare_shared_libraries(self, target, runfiles_dir):
        """Prepare correct shared libraries for running target"""

        # Make symbolic links for shared libraries of the executable.

        # For normal built shared libraries, their paths have been written into the executable.
        # For example, `build64_release/common/crypto/hash/libhash.so`, we need to put a symbolic
        # link `build64_release` pointing to its absolute path.
        build_dir_name = os.path.basename(self.build_dir)
        os.symlink(os.path.abspath(self.build_dir),
                   os.path.join(runfiles_dir, build_dir_name))

        # For shared libraries with a `soname`, their paths are not written into the executable;
        # they are always searched for in a set of configured directories.
        #
        # libcrypto.so.1.0.0 => /lib64/libcrypto.so.1.0.0 (0x00007f0705d9f000)
        for soname, full_path in self._get_shared_libraries_with_soname(target):
            src = os.path.abspath(full_path)
            dst = os.path.join(runfiles_dir, soname)
            if os.path.lexists(dst):
                console.warning('Trying to make duplicate symlink for shared library:\n'
                                '%s -> %s\n'
                                '%s -> %s already exists\n'
                                'skipped, should check duplicate prebuilt '
                                'libraries'
                                % (dst, src, dst, os.path.realpath(dst)))
                continue
            os.symlink(src, dst)

    def _get_shared_libraries_with_soname(self, target):
        """Get shared libraries with soname for one target that it depends."""
        file_list = []
        for dep in target.expanded_deps:
            dep_target = self.target_database[dep]
            if hasattr(dep_target, 'soname_and_full_path'):
                value = dep_target.soname_and_full_path()
                if value:
                    file_list.append(value)
        return file_list

    def _prepare_test_data(self, target):
        if 'testdata' not in target.attr:
            return
        runfiles_dir = self._runfiles_dir(target)
        dest_list = []
        for i in target.attr['testdata']:
            if isinstance(i, tuple):
                src, dest = i
            else:
                src = dest = i
            if '..' in src:
                target.warning('Relative path is not allowed in testdata. Ignored %s.' % src)
                continue
            if src.startswith('//'):
                src = src[2:]
            else:
                src = os.path.join(target.path, src)
            if dest.startswith('//'):
                dest = dest[2:]
            dest = os.path.normpath(dest)
            self.__check_test_data_dest(target, dest, dest_list)
            dest_list.append(dest)
            dest_path = os.path.join(runfiles_dir, dest)
            if os.path.exists(dest_path):
                target.warning('"%s" already existed, could not prepare testdata.' % dest)
                continue
            try:
                os.makedirs(os.path.dirname(dest_path))
            except OSError:
                pass

            if os.path.isfile(src):
                shutil.copy2(src, dest_path)
            elif os.path.isdir(src):
                shutil.copytree(src, dest_path)

        self._prepare_extra_test_data(target)

    def _prepare_extra_test_data(self, target):
        """Prepare extra test data specified in the .testdata file if it exists."""
        testdata = os.path.join(self.build_dir, target.path,
                                '%s.testdata' % target.name)
        if os.path.isfile(testdata):
            runfiles_dir = self._runfiles_dir(target)
            with open(testdata) as f:
                for line in f:
                    data = line.strip().split()
                    if len(data) == 1:
                        src, dst = data[0], ''
                    else:
                        src, dst = data[0], data[1]
                    dst = os.path.join(runfiles_dir, dst)
                    dst_dir = os.path.dirname(dst)
                    if not os.path.isdir(dst_dir):
                        os.makedirs(dst_dir)
                    shutil.copy2(src, dst)

    def _clean_target(self, target):
        """Clean the executive environment."""
        build_dir_name = os.path.basename(self.build_dir)
        link_path = os.path.join(self._runfiles_dir(target), build_dir_name)
        if os.path.exists(link_path):
            os.remove(link_path)

    def _clean_for_coverage(self):
        """Clean executive environment for coverage generating."""
        for target in self._build_targets.values():
            self._clean_target(target)

    def run_target(self, target_name):
        """Run one single target."""
        target = self._build_targets[target_name]
        if target.type not in self.run_list:
            target.error('is not a executable target')
            return 126
        run_env = self._prepare_env(target)
        cmd = [os.path.abspath(self._executable(target))] + self.options.args
        shell = target.data.get('run_in_shell', False)
        if shell:
            cmd = subprocess.list2cmdline(cmd)
        console.info("Run '%s'" % cmd)
        sys.stdout.flush()

        p = subprocess.Popen(cmd, env=run_env, close_fds=True, shell=shell)
        p.wait()
        self._clean_for_coverage()
        return p.returncode
