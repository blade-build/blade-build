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


import os
import shutil
import subprocess
import sys

from blade import config
from blade import console
from blade.util import environ_add_path


class BinaryRunner:
    """BinaryRunner."""

    def __init__(self, options, target_database, build_targets):
        """Init method."""
        from blade import build_manager  # pylint: disable=import-outside-toplevel
        self._build_targets = build_targets
        self.build_dir = build_manager.instance.get_build_dir()
        self.options = options
        self.target_database = target_database

    def _executable(self, target):
        """Returns the executable path."""
        executable_name = target.attr.get('executable_name', target.name)
        return os.path.join(self.build_dir, target.path, executable_name)

    def _runfiles_dir(self, target):
        """Returns runfiles dir."""
        return '%s.runfiles' % self._executable(target)

    @staticmethod
    def _symlink_or_copy_file(src, dst):
        """Create a symlink from dst to src, or copy the file on failure."""
        try:
            os.symlink(src, dst)
        except OSError:
            shutil.copy2(src, dst)

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
                target.error(f'"{dest}" could not exist with "{item}" in testdata')

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
        if sys.platform == 'darwin':
            # dyld ignores LD_LIBRARY_PATH; it searches DYLD_LIBRARY_PATH by leaf
            # name even for @rpath installs, so the runfiles soname symlinks
            # resolve prebuilt dylibs (e.g. vcpkg shared libs) at run time.
            environ_add_path(run_env, 'DYLD_LIBRARY_PATH', runfiles_dir)
        if os.name == 'nt':
            # Windows analog of LD_LIBRARY_PATH: the loader searches PATH for the
            # flattened dependency DLLs placed in runfiles (see
            # _prepare_windows_dlls).
            environ_add_path(run_env, 'PATH', os.path.abspath(runfiles_dir))
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
        """Symlink shared libraries into the runfiles dir so the target finds them.

        Tests/binaries run with ``cwd=runfiles_dir``. blade links its own dynamic
        libraries by their relative build path (e.g. ``build_release/pkg/libfoo.so``)
        with no soname/install_name, so that path is baked into the binary and both
        ld.so (Linux) and dyld (macOS) resolve it relative to ``cwd``. A
        ``runfiles/<build_dir>`` symlink to the real build dir makes those paths
        resolve -- this covers every blade-built library on Linux and macOS alike.
        Prebuilt libraries that carry a soname are referenced by bare soname, so
        they additionally get a ``runfiles/<soname>`` symlink found via
        ``LD_LIBRARY_PATH=runfiles``.

        Windows uses a different DLL lookup (exe dir, PATH) and the PE import
        table carries no path, so the symlink-the-build-dir scheme does not
        apply; instead the dependency DLLs are flattened into runfiles and that
        dir is prepended to PATH at run time (see `_prepare_windows_dlls`).
        """
        if os.name == 'nt':
            self._prepare_windows_dlls(target, runfiles_dir)
            return

        # Symlink the build dir into runfiles so cwd-relative `<build_dir>/.../libX`
        # references resolve at run time (blade-built libraries have no soname, so
        # the build path is what is recorded in the binary). See issue #1167.
        build_dir_link = os.path.join(runfiles_dir, os.path.basename(self.build_dir))
        if not os.path.lexists(build_dir_link):
            os.symlink(os.path.abspath(self.build_dir), build_dir_link)

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
            self._symlink_or_copy_file(src, dst)

    def _prepare_windows_dlls(self, target, runfiles_dir):
        """Flatten the transitive dependency DLLs into the runfiles dir.

        Windows has no rpath and the PE import table records only a DLL's base
        name, so the loader must find each DLL on PATH (or next to the exe).
        blade names every DLL with its package path encoded in, so they never
        collide when flattened into one directory; copy them in and the run env
        prepends runfiles to PATH.
        """
        assert target.expanded_deps is not None, 'expanded_deps not expanded'
        for dep in target.expanded_deps:
            dll = self.target_database[dep].data.get('windows_dll')
            if not dll:
                continue
            dst = os.path.join(runfiles_dir, os.path.basename(dll))
            if not os.path.lexists(dst):
                self._symlink_or_copy_file(os.path.abspath(dll), dst)

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
        if not target.is_executable:
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
