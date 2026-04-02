# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>
# Date:   Feb 14, 2021

"""C/C++ header file inclusion dependency declaration check."""

import os

from blade import console
from blade import util
from blade.util import pickle


def find_libs_by_header(hdr, hdr_targets_map, hdr_dir_targets_map):
    """Find the libraries to which the header file belongs."""
    libs = hdr_targets_map.get(hdr)
    if libs:
        return libs
    hdr_dir = os.path.dirname(hdr)
    while True:
        libs = hdr_dir_targets_map.get(hdr_dir)
        if libs:
            return libs
        old_hdr_dir = hdr_dir
        hdr_dir = os.path.dirname(hdr_dir)
        if hdr_dir == old_hdr_dir:
            return set()


class GlobalDeclaration(object):
    """Global inclusion dependenct relationship declaration."""

    def __init__(self, declaration_file):
        self._declaration_file = declaration_file
        self._initialized = False

    def lazy_init(self, reason):
        if self._initialized:
            return
        console.debug("Load global declaration file, " + reason)
        declaration = pickle.load(open(self._declaration_file, 'rb'))
        # pylint: disable=attribute-defined-outside-init
        self._hdr_targets_map = declaration['public_hdrs']
        self._hdr_dir_targets_map = declaration['public_incs']
        self._private_hdrs_target_map = declaration['private_hdrs']
        self._allowed_undeclared_hdrs = declaration['allowed_undeclared_hdrs']
        self._initialized = True

    def find_libs_by_header(self, hdr):
        self.lazy_init('find_libs_by_header ' + hdr)
        return find_libs_by_header(hdr, self._hdr_targets_map, self._hdr_dir_targets_map)

    def find_targets_by_private_hdr(self, hdr):
        """Find targets by private header file."""
        self.lazy_init('find_targets_by_private_hdr ' + hdr)
        return self._private_hdrs_target_map.get(hdr, set())

    def is_allowed_undeclared_hdr(self, hdr):
        self.lazy_init('is_allowed_undeclared_hdr ' + hdr)
        return hdr in self._allowed_undeclared_hdrs


_MSVC_INCUSION_PREFIX = 'Note: including file:'


def _is_inclusion_line(line):
    """Return True if the line is a header inclusion line."""
    return _is_msvc_inclusion_line(line)


def _is_msvc_inclusion_line(line):
    return line.startswith(_MSVC_INCUSION_PREFIX)


def _is_gcc_inclusion_line(line):
    """Return True if the line is a header inclusion line."""
    return line.startswith('#include')


def _parse_inclusion_stacks(path, build_dir):
    """Parae headers inclusion stacks from file.

    Given the following inclusions found in the app/example/foo.cc.o.H:

        . ./app/example/foo.h
        .. build64_release/app/example/proto/foo.pb.h
        ... build64_release/common/rpc/rpc_service.pb.h
        . build64_release/app/example/proto/bar.pb.h
        . ./common/rpc/rpc_client.h
        .. build64_release/common/rpc/rpc_options.pb.h

    Return a list of all directly included header files and a list with each item being a list
    representing where the header is included from in the current translation unit.

    Note that we will STOP tracking at the first generated header (if any)
    while other headers included from the header directly or indirectly are
    ignored since that part of dependency is ensured by the generator, such
    as proto_library.

    As shown in the example above, it returns the following directly header list:

        [
            'app/example/foo.h',
            'build64_release/app/example/proto/bar.pb.h',
            'common/rpc/rpc_client.h',
        ]

    and the inclusion stacks:

        [
            ['app/example/foo.h', 'build64_release/app/example/proto/foo.pb.h'],
            ['build64_release/app/example/proto/bar.pb.h'],
            ['common/rpc/rpc_client.h', 'build64_release/common/rpc/rpc_options.pb.h'],
        ]
    """
    direct_hdrs = []  # The directly included header files
    stacks, hdrs_stack = [], []

    def _process_hdr(level, hdr, current_level):
        if os.path.isabs(hdr):
            skip_level = level
        elif hdr.startswith(build_dir):
            skip_level = level
            stacks.append(hdrs_stack + [_remove_build_dir_prefix(os.path.normpath(hdr), build_dir)])
        else:
            current_level = level
            hdrs_stack.append(_remove_build_dir_prefix(os.path.normpath(hdr), build_dir))
            skip_level = -1
        return current_level, skip_level

    current_level = 0
    current_line = ''
    skip_level = -1
    with open(path) as f:
        for index, line in enumerate(f):
            line = line.rstrip()  # Strip `\n`
            if not _is_inclusion_line(line):
                # The remaining lines are useless for us
                break
            level, hdr = _parse_hdr_level_line(line)
            if level == -1:
                console.log('%s: Unrecognized line %s' % (path, line))
                break

            if level == 1 and not os.path.isabs(hdr):
                direct_hdrs.append(_remove_build_dir_prefix(os.path.normpath(hdr), build_dir))
            if level > current_level:
                if skip_level != -1 and level > skip_level:
                    continue
                try:
                    assert level == current_level + 1
                except AssertionError:
                    console.error(
                        'path: %s, line_number: %d\n'
                        'level: %d, current_level: %d\n'
                        'line: %s\ncurrent_line: %s' % (
                            path, index+1,
                            level, current_level,
                            line, current_line))
                    raise
                current_level, skip_level = _process_hdr(level, hdr, current_level)
                current_line = line
            else:
                while current_level >= level:
                    current_level -= 1
                    hdrs_stack.pop()
                current_level, skip_level = _process_hdr(level, hdr, current_level)
                current_line = line

    return direct_hdrs, stacks


def _parse_hdr_level_line(line):
    """Parse a normal line of a header stack file

    Example:
        . ./common/rpc/rpc_client.h
    """
    return _parse_msvc_hdr_level_line(line)


def _parse_gcc_hdr_level_line(line):
    pos = line.find(' ')
    if pos == -1:
        return -1, ''
    level = pos
    hdr = line[pos + 1:]
    if hdr.startswith('./'):
        hdr = hdr[2:]
    return level, hdr


def _parse_msvc_hdr_level_line(line):
    line = line.removeprefix(_MSVC_INCUSION_PREFIX)
    hdr = line.lstrip()
    level = len(line) - len(hdr)
    cwd = os.getcwd().lower()
    if hdr.lower().startswith(cwd):
        hdr = hdr[len(cwd)+1:]
    return level, hdr


def _remove_build_dir_prefix(path, build_dir):
    """Remove the build dir prefix of path (e.g. build64_release/)
    Args:
        path:str, the full path starts from the workspace root
    """
    prefix = build_dir + os.sep
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


class Checker(object):
    """C/C++ Header file inclusion dependency checker"""

    def __init__(self, target):
        self.type = target['type']
        self.name = target['name']
        self.path = target['path']
        self.key = target['key']
        self.deps = target['deps']
        self.build_dir = target['build_dir']
        self.expanded_srcs = target['expanded_srcs']
        self.expanded_hdrs = target['expanded_hdrs']
        self.source_location = target['source_location']
        self.declared_hdrs = target['declared_hdrs']
        self.declared_incs = target['declared_incs']
        self.declared_genhdrs = target['declared_genhdrs']
        self.declared_genincs = target['declared_genincs']
        self.hdrs_deps = target['hdrs_deps']
        self.private_hdrs_deps = target['private_hdrs_deps']
        self.allowed_undeclared_hdrs = target['allowed_undeclared_hdrs']
        self.suppress = target['suppress']
        self.severity = target['severity']

        inclusion_declaration_file = os.path.join(self.build_dir, 'inclusion_declaration.data')
        self.global_declaration = GlobalDeclaration(inclusion_declaration_file)

    def _find_inclusion_file(self, src, is_header):
        """Find the '.H' file for the given src.

        The `.H` file is generated from gcc's `-H` option, see
        https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html
        for details.
        """
        # NOTE: The inclusion file for header file and impl file has different extension name.
        objs_dir = os.path.join(self.build_dir, self.path, self.name + '.objs')
        path = ('%s.H' if is_header else '%s.o.H') % os.path.join(objs_dir, src)
        if not os.path.exists(path):
            return ''
        return path

    def _hdr_is_declared(self, hdr):
        return self._hdr_is_declared_in(hdr, self.declared_hdrs, self.declared_incs)

    def _hdr_is_transitive_declared(self, hdr):
        return self._hdr_is_declared_in(hdr, self.declared_genhdrs, self.declared_genincs)

    def _hdr_is_declared_in(self, hdr, declared_hdrs, declared_incs):
        if hdr in declared_hdrs:
            return True
        for dir in declared_incs:
            if hdr.startswith(dir):
                return True
        return False

    def _check_direct_headers(self, full_src, direct_hdrs, suppressd_hdrs,
                              missing_dep_hdrs, undeclared_hdrs, check_msg):
        """Verify directly included header files is in deps."""
        msg = []
        for hdr in direct_hdrs:
            if hdr in self.declared_hdrs:
                console.diagnose(self.source_location, 'debug', '"%s" is a declared header' % (hdr))
                continue
            libs = self.find_libs_by_header(hdr)
            if not libs:
                libs = self.find_targets_by_private_hdr(hdr)
                if libs and self.key not in libs:
                    msg.append('    "%s" is a private header file of %s' % (
                        hdr, self._or_joined_libs(libs)))
                    continue
                console.diagnose(self.source_location, 'debug',
                                 '"%s" is an undeclared header' % hdr)
                undeclared_hdrs.add(hdr)
                # We need also check suppressd_hdrs because target maybe not loaded in partial build
                if hdr not in suppressd_hdrs and not self.is_allowed_undeclared_hdr(hdr):
                    msg.append('    %s' % self._header_undeclared_message(hdr))
                continue
            deps = set(self.deps + [self.key])  # Don't forget target itself
            if not (libs & deps):  # pylint: disable=superfluous-parens
                # NOTE:
                # We just don't report a suppressd hdr, but still need to record it as a failure.
                # Because a passed src will not be verified again, even if we remove it from the
                # suppress list.
                # Same reason in the _check_generated_headers.
                missing_dep_hdrs.add(hdr)
                if hdr not in suppressd_hdrs:
                    msg.append('    For %s' % self._hdr_declaration_message(hdr, libs))
        if msg:
            check_msg.append('  In file included from "%s",' % full_src)
            check_msg += msg

    def find_libs_by_header(self, hdr):
        # Find from the local incchk file firstly to avoid loading the large global declaration.
        # The same below.
        if hdr in self.hdrs_deps:
            return self.hdrs_deps[hdr]
        return self.global_declaration.find_libs_by_header(hdr)

    def find_targets_by_private_hdr(self, hdr):
        if hdr in self.private_hdrs_deps:
            return self.private_hdrs_deps[hdr]
        return self.global_declaration.find_targets_by_private_hdr(hdr)

    def is_allowed_undeclared_hdr(self, hdr):
        if hdr in self.allowed_undeclared_hdrs:
            return self.allowed_undeclared_hdrs[hdr]
        return self.global_declaration.is_allowed_undeclared_hdr(hdr)

    def _header_undeclared_message(self, hdr):
        msg = '"%s" is not declared in any cc target. ' % util.to_unix_path(hdr)
        if util.path_under_dir(hdr, self.path):
            msg += 'If it belongs to this target, it should be declared in "src"'
            if self.type.endswith('_library'):
                msg += ' if it is private or in "hdrs" if it is public'
            msg += ', otherwise '
        msg += 'it should be declared in "hdrs" of the appropriate library to which it belongs'
        return msg

    def _hdr_declaration_message(self, hdr, libs=None):
        if libs is None:
            libs = self.find_libs_by_header(hdr)
        if not libs:
            return '"%s"' % hdr
        return '"%s", which belongs to %s' % (hdr, self._or_joined_libs(libs))

    def _or_joined_libs(self, libs):
        """Return " or " joind libs descriptive string."""
        def beautify(lib):
            # Convert full path to ':' started form if it is in same directory as this target.
            if lib.startswith(self.path + ':'):
                return lib[len(self.path):]
            return '//' + lib
        return ' or '.join(['"%s"' % beautify(lib) for lib in libs])

    def _check_generated_headers(self, full_src, stacks, direct_hdrs, suppressd_hdrs,
                                 missing_dep_hdrs, check_msg):
        """
        Verify indirectly included generated header files is in deps.
        """
        msg = []
        for stack in stacks:
            generated_hdr = stack[-1]
            if generated_hdr in direct_hdrs:  # Already verified as direct_hdrs
                continue
            if self._hdr_is_transitive_declared(generated_hdr):
                continue
            stack.pop()
            missing_dep_hdrs.add(generated_hdr)
            if generated_hdr in suppressd_hdrs:
                continue
            msg.append('  For %s' % self._hdr_declaration_message(generated_hdr))
            if not stack:
                msg.append('    In file included from "%s"' % util.to_unix_path(full_src))
            else:
                stack.reverse()
                msg.append('    In file included from %s' % self._hdr_declaration_message(stack[0]))
                prefix = '                     from %s'
                msg += [prefix % self._hdr_declaration_message(h) for h in stack[1:]]
                msg.append(prefix % ('"%s"' % full_src))
        check_msg += msg

    def check(self):
        """
        Check whether included header files is declared in "deps" correctly.

        Returns:
            Whether nothing is wrong.
        """
        missing_details = {}  # {src: list(hdrs)}
        undeclared_hdrs = set()
        all_direct_hdrs = set()
        all_generated_hdrs = set()

        direct_check_msg = []
        generated_check_msg = []

        def check_file(src, full_src, is_header):
            if util.path_under_dir(full_src, self.build_dir):  # Don't check generated files.
                return
            path = self._find_inclusion_file(src, is_header)
            if not path:
                console.warning('No inclusion file found for %s' % full_src)
                return
            console.debug('Find inclusuon file %s for %s' % (path, full_src))
            direct_hdrs, stacks = _parse_inclusion_stacks(path, self.build_dir)
            all_direct_hdrs.update(direct_hdrs)
            missing_dep_hdrs = set()
            self._check_direct_headers(
                full_src, direct_hdrs, self.suppress.get(src, []),
                missing_dep_hdrs, undeclared_hdrs, direct_check_msg)

            for stack in stacks:
                all_generated_hdrs.add(stack[-1])
            # But direct headers can not cover all, so it is still useful
            self._check_generated_headers(
                full_src, stacks, direct_hdrs,
                self.suppress.get(src, []),
                missing_dep_hdrs, generated_check_msg)

            if missing_dep_hdrs:
                missing_details[src] = list(missing_dep_hdrs)

        for src, full_src in self.expanded_srcs:
            check_file(src, full_src, is_header=False)

        for hdr, full_hdr in self.expanded_hdrs:
            check_file(hdr, full_hdr, is_header=True)

        severity = self.severity
        if direct_check_msg:
            console.diagnose(self.source_location, severity,
                             '%s: Missing dependency declaration:\n%s' % (self.name, '\n'.join(direct_check_msg)))
        if generated_check_msg:
            console.diagnose(self.source_location, severity,
                             '%s: Missing indirect dependency declaration:\n%s' % (self.name, '\n'.join(generated_check_msg)))

        ok = (severity != 'error' or not direct_check_msg and not generated_check_msg)

        details = {}
        if missing_details:
            details['missing_dep'] = missing_details
        if undeclared_hdrs:
            details['undeclared'] = sorted(undeclared_hdrs)
        details['direct_hdrs'] = all_direct_hdrs
        details['generated_hdrs'] = all_generated_hdrs
        return ok, details


def check(target_check_info_file):
    target = pickle.load(open(target_check_info_file, 'rb'))
    extra_file = target_check_info_file + '.extra'
    if os.path.exists(extra_file):
        with open(extra_file, 'rb') as f:
            extra_target = pickle.load(f)
        target.update(extra_target)
    checker = Checker(target)
    return checker.check()
