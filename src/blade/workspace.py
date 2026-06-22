# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>
# Date:   Feb 12, 2021

"""The workspace module represent current workspace."""


import errno
import json
import os
import re
import string

from blade import config
from blade import console
from blade import sanitizer
from blade import util


def _build_variant_suffix(options):
    """Suffix appended to the build dir name for variant builds.

    Each active variant contributes a `_<tag>` segment; with no variant the
    result is the empty string, so the normal build dir keeps its plain name
    (e.g. ``build_release``). New variants only need to append their tag here.
    """
    variants = []
    if getattr(options, 'coverage', False):
        variants.append('coverage')
    sanitizers = getattr(options, 'sanitizers', None)
    if sanitizers:
        variants.append(sanitizer.build_tag(sanitizers))  # e.g. 'asan'
    # PGO instrument/optimize builds are codegen-incompatible with a normal
    # build, so they get their own build dir (like coverage/asan). Both phases
    # share ONE `_pgo` dir on purpose: gcc keys its `.gcda` lookup by the object
    # file path, so the generate and use builds must place objects at identical
    # paths or gcc can't find the profile (-Wmissing-profile). (clang is keyed
    # by function, so it wouldn't care -- but a single dir is correct for both.)
    if (getattr(options, 'profile-generate', None) is not None or
            getattr(options, 'profile-use', None) is not None):
        variants.append('pgo')
    return ''.join('_' + v for v in variants)


def _build_dir_name(build_path_format, options, toolchain):
    """Compute the build-dir name: template substitution + variant suffix.

    The selected ``toolchain`` supplies the platform triple
    (``${os}``/``${arch}``/``${bits}``); ``${profile}`` comes from the options.
    The sanitizer/coverage variant tag is appended afterwards -- it is never part
    of the template, so it composes uniformly regardless of the template a
    project chooses.
    """
    template = string.Template(build_path_format)
    try:
        name = template.substitute(
            profile=options.profile,
            os=toolchain.target_os,
            arch=toolchain.target_arch,
            bits=options.bits)
    except KeyError as e:
        console.fatal(
            'global_config.build_path_template "%s" references unknown variable '
            '%s; supported: ${profile} ${os} ${arch} ${bits} (sanitizer/coverage '
            'variants are appended automatically)' % (build_path_format, e))
    return name + _build_variant_suffix(options)


def _generate_scm_svn():
    url = revision = 'unknown'
    try:
        returncode, stdout, stderr = util.run_command(['svn', 'info'])
    except OSError as e:  # svn not installed / not on PATH
        console.debug('Failed to run svn for scm info: %s' % e)
        return url, revision
    if returncode != 0:
        console.debug('Failed to generate svn scm: %s' % stderr)
    else:
        for line in stdout.splitlines():
            if line.startswith('URL: '):
                url = line.strip().split()[-1]
            if line.startswith('Revision: '):
                revision = line.strip().split()[-1]
                break

    return url, revision


def _generate_scm_git():
    url = revision = 'unknown'

    def git(cmd):
        try:
            returncode, stdout, stderr = util.run_command(cmd)
        except OSError as e:  # git not installed / not on PATH
            console.debug('Failed to run git for scm info: %s' % e)
            return ''
        if returncode != 0:
            console.debug('Failed to generate git scm: %s' % stderr)
            return ''
        return stdout

    out = git(['git', 'rev-parse', 'HEAD'])
    if out:
        revision = out.strip()
    out = git(['git', 'remote', '-v'])
    # $ git remote -v
    # origin  https://github.com/blade-build/blade-build.git (fetch)
    # origin  https://github.com/blade-build/blade-build.git (push)
    if out:
        url = out.splitlines()[0].split()[1]
        # Remove userinfo (such as username and password) from url, if any.
        url = re.sub(r'(?<=://).*:.*@', '', url)
    return url, revision


def _generate_scm(build_dir):
    if os.path.isdir('.git'):
        url, revision = _generate_scm_git()
    elif os.path.isdir('.svn'):
        url, revision = _generate_scm_svn()
    else:
        console.debug('Unknown scm.')
        return
    path = os.path.join(build_dir, 'scm.json')
    with open(path, 'w') as f:
        json.dump({
            'revision': revision,
            'url': url,
        }, f)


class Workspace:
    """Workspace represent a dir tree rooted from the dir where the BLADE_ROOT residents."""
    def __init__(self, options):
        self.__options = options
        working_dir = util.get_cwd()
        self.__root_dir = self._find_root_dir(working_dir)
        self.__working_dir = os.path.relpath(working_dir, self.__root_dir)  # pyright: ignore[reportCallIssue, reportArgumentType]
        self.__build_dir = ''

    @property
    def root_dir(self):
        return self.__root_dir

    @property
    def build_dir(self):
        return self.__build_dir

    @property
    def working_dir(self):
        return self.__working_dir

    def switch_to_root_dir(self):
        """Switch current dir to root dir of workspace."""
        if self.__root_dir != self.__working_dir:
            # This message is required by vim quickfix mode if pwd is changed during
            # the building, DO NOT change the pattern of this message.
            if self.__options.verbosity > console.Verbosity.QUIET:
                print("Blade: Entering directory `%s'" % self.__root_dir)
            os.chdir(self.__root_dir)

    def setup_build_dir(self, toolchain):
        """Setup build dir.

        ``toolchain`` is the cc toolchain created in main; it is the source of
        truth for the ``${os}``/``${arch}``/``${bits}`` build-dir variables.
        """
        build_path_format = config.get_item('global_config', 'build_path_template')
        build_dir = _build_dir_name(build_path_format, self.__options, toolchain)

        if not os.path.exists(build_dir):
            os.mkdir(build_dir)
            # v3 renamed the default build dir build64_<profile> -> build_<profile>
            # (the legacy `64` couldn't tell arm64 from x86_64). Nudge once, when
            # the new dir is first created beside a stale legacy one, unless the
            # project pinned the old name back.
            legacy = 'build64_' + self.__options.profile
            if not build_dir.startswith('build64') and os.path.isdir(legacy):
                console.notice(
                    'Blade now defaults to "%s"; the pre-v3 "%s" is stale -- '
                    'delete it, or set global_config(build_path_template='
                    '"build${bits}_${profile}") to keep the old name.'
                    % (build_dir, legacy))
        # Drop a `.bladeskip` sentinel so the BUILD-file walker skips this
        # directory without needing to know its name (see issue #518).
        # Touched on every setup so projects that pre-create the build dir
        # by hand still get marked. The marker is also what the walker uses
        # for any user-designated skip directory, so the build dir gets
        # exactly the same treatment with no special-case logic.
        skip_marker = os.path.join(build_dir, '.bladeskip')
        if not os.path.exists(skip_marker):
            try:
                with open(skip_marker, 'w', encoding='utf-8') as f:
                    f.write('# Auto-generated by blade to mark this directory '
                            'as a build output that should be skipped by the '
                            'BUILD-file walker. Safe to leave in place.\n')
            except OSError as e:
                console.warning(f"Can't create '{skip_marker}', {e}")
        try:
            os.remove('blade-bin')
        except OSError:
            pass
        try:
            os.symlink(os.path.abspath(build_dir), 'blade-bin')
        except OSError as e:
            console.warning("Can't create symbolic link 'blade-bin', %s" % e)

        log_file = os.path.join(build_dir, 'blade.log')
        console.set_log_file(log_file)
        _generate_scm(build_dir)

        self.__build_dir = build_dir
        return build_dir

    def lock(self):
        """Lock current workspace."""
        _BUILDING_LOCK_FILE = '.blade.building.lock'
        lock_file_fd, ret_code = util.lock_file(os.path.join(self.__build_dir, _BUILDING_LOCK_FILE))
        if lock_file_fd == -1:
            if ret_code == errno.EAGAIN:
                console.fatal('There is already an active building in current workspace.')
            else:
                console.fatal('Lock exception, please try it later.')
        return lock_file_fd

    def unlock(self, lock_id):
        """Unlock current workspace."""
        util.unlock_file(lock_id)

    def _find_root_dir(self, working_dir):
        """Find the dir holds the BLADE_ROOT file.

        The blade_root_dir is the directory which is the closest upper level
        directory of the current working directory, and containing a file
        named BLADE_ROOT.
        """
        blade_root = util.find_file_bottom_up('BLADE_ROOT', from_dir=working_dir)
        if not blade_root:
            console.fatal(
                "Can't find the file 'BLADE_ROOT' in this or any upper directory.\n"
                "Blade need this file as a placeholder to locate the root source directory "
                "(aka the directory where you #include start from).\n"
                "You should create it manually at the first time.")
        return os.path.dirname(blade_root)


__instance = None


def initialize(options):
    global __instance
    assert __instance is None
    __instance = Workspace(options)
    return __instance


def current():
    """Get the current workspace instance."""
    return __instance
