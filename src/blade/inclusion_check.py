# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>
# Date:   Feb 14, 2021

"""C/C++ header file inclusion dependency declaration check."""

import os
import pickle
import posixpath
import re

from blade import console


# `#include "..."` and `#include <...>` directives in a source/header. Both
# forms are matched because the angle form is syntactically also valid for
# project headers (some code uses `<project/owner.h>`); the caller filters
# the result down to paths the compiler actually traversed, so a system
# header spelled either way is harmless. The `^\s*#` anchor with re.MULTILINE
# excludes commented-out forms like `// #include "x.h"` (the line no longer
# starts with `#`), block-comment lines decorated with `*` (e.g.
# ` * #include ...`), and trailing same-line uses like `foo(); #include ...`.
_INCLUDE_RE = re.compile(
    r'^\s*#\s*include\s*(?:"([^"]+)"|<([^>]+)>)', re.MULTILINE)


def _scan_source_includes(full_src):
    """Return the set of headers `#include`'d by *full_src* (both forms).

    Intentionally naive: this is a pure regex scan and makes no attempt to
    evaluate the preprocessor -- includes inside multi-line block comments,
    `#if 0` blocks, untaken `#ifdef` branches, etc. are *all* returned as if
    they were live. That is by design.

    The hdrs check is anchored on **what the compiler actually used**: the
    `.incstk` recorded by `-H` is the source of truth, and this scan is a
    *supplement* for the one case where `-H` lies -- headers elided from
    depth-1 by the multiple-include-guard optimization (see issue #1171).
    The caller intersects this scan with the set of paths the compiler
    actually traversed (`_read_all_incstk_paths`), so anything the compiler
    did not compile (dead branch, commented code, mis-quoted system header
    etc.) drops out at the intersection. Trying to be smarter here (strip
    `#if 0`, strip block comments) is therefore redundant and risks getting
    `#if 0 / #else / #endif` wrong -- the intersection is the gate.

    Known limitation: macro-form `#include MY_HEADER` is invisible to regex;
    `-H` picks those up except when both macro-form AND guard-suppression
    occur together (a rare-squared intersection accepted by this fix).
    """
    try:
        with open(full_src, encoding='utf-8', errors='replace') as f:
            text = f.read()
    except OSError:
        return set()
    # `posixpath.normpath`, not `os.path.normpath`: `#include` paths are
    # always `/`-separated regardless of host OS (and blade's internal
    # representation is unix-style; see `to_unix_path`). Both collapse
    # internal `//` and `./` segments.
    return {posixpath.normpath(quoted or angle)
            for quoted, angle in _INCLUDE_RE.findall(text)}


def _read_all_incstk_paths(incstk_path, build_dir, system_incs=()):
    """Return the set of all relative paths the compiler traversed.

    Used to filter source-scanned `#include`s down to paths the compiler
    actually saw -- so `#include "stdio.h"` (system header, absolute path in
    `-H`) is not treated as a project header just because it was quoted, and
    `#include`s inside `#if 0` or other dead branches are not treated as real
    because they never reached the compiler. See `_scan_source_includes` and
    issue #1171.
    """
    paths = set()
    try:
        with open(incstk_path) as f:
            for line in f:
                line = line.rstrip()
                if not _is_inclusion_line(line):
                    break
                level, hdr = _parse_hdr_level_line(line, system_incs)
                if level == -1 or os.path.isabs(hdr):
                    continue
                # See `_scan_source_includes` for why posixpath.normpath.
                paths.add(_remove_build_dir_prefix(posixpath.normpath(hdr), build_dir))
    except OSError:
        pass
    return paths


# Inlined from `util` (both are one-liners) so this module -- imported on the
# hot `cc_inclusion_check` path -- does not pull in the whole `util` module.
def to_unix_path(path):
    """Convert path separators to Unix-style forward slashes."""
    return path.replace('\\', '/')


# The backend writes declaration data (`declared_hdrs`, `public_hdrs`, ...)
# with `os.sep` -- backslashes on Windows -- but inclusion stacks are parsed to
# forward slashes.  These helpers reconcile both sides here, in the consumer,
# so the path comparisons work regardless of the platform that produced them.
#
# On POSIX every path is already '/'-separated (os.path generates '/', so does
# `-H`), making normalization a pure no-op -- but one that would still rebuild
# each container, including the potentially large global `public_hdrs` map on
# every check. So skip it entirely off Windows and return the input unchanged.
_PATHS_NEED_UNIX_NORM = os.sep != '/'


def _unix_path_set(paths):
    """Normalize a set/list of paths to forward slashes (None passes through)."""
    if paths is None or not _PATHS_NEED_UNIX_NORM:
        return paths
    return {to_unix_path(p) for p in paths}


def _unix_path_dict(mapping):
    """Normalize the path keys of a dict to forward slashes (None passes through)."""
    if mapping is None or not _PATHS_NEED_UNIX_NORM:
        return mapping
    return {to_unix_path(k): v for k, v in mapping.items()}


def _unix_path_pairs(pairs):
    """Normalize a list of (name, full_path) pairs to forward slashes."""
    if not _PATHS_NEED_UNIX_NORM:
        return pairs
    return [(to_unix_path(name), to_unix_path(full)) for name, full in pairs]


def path_under_dir(path, dir):
    """Check whether *path* is under *dir*.

    Both must be normalized, and both relative or both absolute.
    """
    return dir == '.' or path == dir or path.startswith(dir) and path[len(dir)] == '/'


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


class GlobalDeclaration:
    """Global inclusion dependenct relationship declaration."""
    def __init__(self, declaration_file):
        self._declaration_file = declaration_file
        self._initialized = False

    def lazy_init(self, reason):
        if self._initialized:
            return
        console.debug("Load global declaration file, " + reason)
        with open(self._declaration_file, 'rb') as f:
            declaration = pickle.load(f)
        # pylint: disable=attribute-defined-outside-init
        # Normalize path keys to forward slashes (the backend writes them with
        # os.sep). `header_less` holds target keys, not paths, so it is left as-is.
        self._hdr_targets_map = _unix_path_dict(declaration['public_hdrs'])
        self._hdr_dir_targets_map = _unix_path_dict(declaration['public_incs'])
        self._private_hdrs_target_map = _unix_path_dict(declaration['private_hdrs'])
        self._header_less = declaration.get('header_less', set())
        self._allowed_undeclared_hdrs = _unix_path_set(declaration['allowed_undeclared_hdrs'])
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

    def is_header_less(self, key: str) -> bool:
        """Whether a library was declared with an explicit empty `hdrs = []`."""
        self.lazy_init('is_header_less ' + key)
        return key in self._header_less


_MSVC_INCUSION_PREFIX = 'Note: including file:'


def _is_inclusion_line(line):
    """Return True if the line is a header inclusion line (GCC or MSVC)."""
    if os.name == 'nt' and line.startswith(_MSVC_INCUSION_PREFIX):
        return True
    return line.startswith('.')


def _parse_inclusion_stacks(path, build_dir, system_incs=()):
    """Parae headers inclusion stacks from file.

    Given the following inclusions found in the app/example/foo.cc.incstk:

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
            stacks.append(hdrs_stack + [_remove_build_dir_prefix(posixpath.normpath(hdr), build_dir)])
        else:
            current_level = level
            hdrs_stack.append(_remove_build_dir_prefix(posixpath.normpath(hdr), build_dir))
            skip_level = -1
        return current_level, skip_level

    current_level = 0
    skip_level = -1
    with open(path) as f:
        for line in f:
            line = line.rstrip()  # Strip `\n`
            if not _is_inclusion_line(line):
                # The remaining lines are useless for us
                break
            level, hdr = _parse_hdr_level_line(line, system_incs)
            if level == -1:
                console.log(f'{path}: Unrecognized line {line}')
                break
            if level == 1 and not os.path.isabs(hdr):
                direct_hdrs.append(_remove_build_dir_prefix(posixpath.normpath(hdr), build_dir))
            if level > current_level:
                if skip_level != -1 and level > skip_level:
                    continue
                if level > current_level + 1:
                    # Depth gap: the intervening header(s) (levels
                    # current_level+1 .. level-1) are absolute/system headers
                    # that were filtered out of the incstk (GCC awk `[^/]`;
                    # MSVC in-workspace filter). This header is reached only
                    # through them, so -- like an absolute header -- it and its
                    # subtree are not tracked includes of this TU. Skip the
                    # subtree instead of aborting the whole build. See #953.
                    if skip_level == -1:
                        skip_level = current_level + 1
                    continue
                current_level, skip_level = _process_hdr(level, hdr, current_level)
            else:
                while current_level >= level:
                    current_level -= 1
                    hdrs_stack.pop()
                current_level, skip_level = _process_hdr(level, hdr, current_level)

    return direct_hdrs, stacks


def _parse_hdr_level_line(line, system_incs=()):
    """Parse a normal line of a header stack file (GCC or MSVC format).

    GCC example:
        . ./common/rpc/rpc_client.h
    MSVC example:
        Note: including file:  common/rpc/rpc_client.h
    """
    if os.name == 'nt' and line.startswith(_MSVC_INCUSION_PREFIX):
        return _parse_msvc_hdr_level_line(line, system_incs)
    return _parse_gcc_hdr_level_line(line)


def _parse_gcc_hdr_level_line(line):
    """Parse a GCC-format header level line."""
    pos = line.find(' ')
    if pos == -1:
        return -1, ''
    level = pos
    hdr = line[pos + 1:]
    if hdr.startswith('./'):
        hdr = hdr[2:]
    return level, hdr


def _parse_msvc_hdr_level_line(line, system_incs=()):
    """Parse an MSVC /showIncludes format header line.

    MSVC format: 'Note: including file:  path\\to\\header.h'
    where the whitespace between the prefix and the path indicates the nesting level.

    `system_incs` are the consumer's system/external include dirs (`/external:I`,
    lower-cased, '/'-separated, absolute). MSVC prints *every* header absolute;
    one under a system dir (e.g. a vcpkg tree) is external, so it is kept
    absolute here -- the caller skips absolute headers as system, exactly as GCC
    reports `-isystem` headers absolute on POSIX. Other headers get the cwd
    prefix stripped to the project-relative path MSVC does not print; doing that
    to an external header would mis-file it as a project one, since these trees
    live under the build dir (hence under cwd). See issue #1321.
    """
    line = line[len(_MSVC_INCUSION_PREFIX):]
    hdr = line.lstrip()
    level = len(line) - len(hdr)
    # Normalize to Unix-style paths for consistency with GCC output
    hdr = to_unix_path(hdr)
    low = hdr.lower()
    for inc in system_incs:
        if low.startswith(inc + '/'):
            return level, hdr  # external header: keep absolute -> skipped
    # Remove current working directory prefix if present
    cwd = to_unix_path(os.getcwd()).lower()
    if low.startswith(cwd):
        hdr = hdr[len(cwd) + 1:]
    return level, hdr


def _remove_build_dir_prefix(path, build_dir):
    """Remove the build dir prefix of path (e.g. build64_release/)
    Args:
        path:str, the full path starts from the workspace root
    """
    prefix = build_dir + '/'
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


class Checker:
    """C/C++ Header file inclusion dependency checker"""

    def __init__(self, target):
        self.type = target['type']
        self.name = target['name']
        self.path = target['path']
        self.key = target['key']
        self.deps = target['deps']
        self.build_dir = to_unix_path(target['build_dir'])
        # Normalize all declared paths to forward slashes so they match the
        # forward-slash header paths parsed from inclusion stacks. The backend
        # writes them with os.sep (backslashes on Windows). See `to_unix_path`.
        self.expanded_srcs = _unix_path_pairs(target['expanded_srcs'])
        self.expanded_hdrs = _unix_path_pairs(target['expanded_hdrs'])
        self.source_location = target['source_location']
        self.declared_hdrs = _unix_path_set(target['declared_hdrs'])
        self.declared_incs = _unix_path_set(target['declared_incs'])
        self.declared_genhdrs = _unix_path_set(target['declared_genhdrs'])
        self.declared_genincs = _unix_path_set(target['declared_genincs'])
        # System/external include dirs (`/external:I`): lower-cased, '/'-sep,
        # absolute. Used to keep MSVC's absolute external headers absolute so the
        # check treats them as system, like GCC's -isystem on POSIX (issue #1321).
        # `.get` for forward compatibility with incchk files from older blades.
        self.system_incs = tuple(
            p.replace('\\', '/').lower() for p in (target.get('system_incs') or []))
        self.hdrs_deps = _unix_path_dict(target['hdrs_deps'])
        self.private_hdrs_deps = _unix_path_dict(target['private_hdrs_deps'])
        self.allowed_undeclared_hdrs = _unix_path_dict(target['allowed_undeclared_hdrs'])
        self.suppress = _unix_path_dict(target['suppress'])
        self.severity = target['severity']
        # Unused-deps check (forward-compatible defaults for older incchk files).
        self.unused_deps_severity = target.get('unused_deps_severity', 'debug')
        self.unused_deps_suppress = set(target.get('unused_deps_suppress', []))
        self.keep_deps = set(target.get('keep_deps', []))

        inclusion_declaration_file = os.path.join(self.build_dir, 'inclusion_declaration.data')
        self.global_declaration = GlobalDeclaration(inclusion_declaration_file)


    def _find_inclusion_file(self, src):
        """Find the `.incstk` inclusion-stack file for the given source or header.

        The name is `<src>.incstk` for both sources and headers (independent of
        the object-file suffix). It is generated from gcc's `-H` option, see
        https://gcc.gnu.org/onlinedocs/gcc/Preprocessor-Options.html
        for details.
        """
        objs_dir = '/'.join([self.build_dir, self.path, self.name + '.objs'])
        path = objs_dir + '/' + src + '.incstk'
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
                    msg.append(f'    "{hdr}" is a private header file of {self._or_joined_libs(libs)}')
                    continue
                console.diagnose(self.source_location, 'debug', '"%s" is an undeclared header' % hdr)
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
        msg = '"%s" is not declared in any cc target. ' % hdr
        if path_under_dir(hdr, self.path):
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
        return f'"{hdr}", which belongs to {self._or_joined_libs(libs)}'

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
                msg.append('    In file included from "%s"' % full_src)
            else:
                stack.reverse()
                msg.append('    In file included from %s' % self._hdr_declaration_message(stack[0]))
                prefix = '                     from %s'
                msg += [prefix % self._hdr_declaration_message(h) for h in stack[1:]]
                msg.append(prefix % ('"%s"' % full_src))
        check_msg += msg

    def _beautify_lib(self, lib: str) -> str:
        """Render a lib key as ":name" (same dir) or "//path:name"."""
        if lib.startswith(self.path + ':'):
            return '"%s"' % lib[len(self.path):]
        return '"//%s"' % lib

    def _check_unused_deps(self, all_direct_hdrs: set[str]) -> set[str]:
        """Return declared deps none of whose public headers is directly included.

        Exemptions:
          * `keep_deps` and configured `unused_deps_suppress`;
          * the target itself;
          * header-less cc_libraries (declared `hdrs = []` -- no public header
            that could be used, so flagging them would be pure noise);
          * system libraries (deps keyed `#:NAME`, e.g. `#:dl`, `#:pthread`):
            their headers (e.g. `<dlfcn.h>`, `<pthread.h>`) do exist, but
            blade has no system-header -> system-lib mapping (such a map
            would be platform- and distro-specific), so a header-based check
            has nothing to consult -- flagging would always be a false
            positive.
          * Header re-export: a dep is exempt if any of THIS target's own
            `hdrs` is ALSO declared as a public header by that dep. The
            shared declaration is blade's only structural signal that the
            current target is acting as an umbrella facade around the dep
            (`fiber:fiber` redeclaring `async.h` from `fiber:async`, etc.).
            Without this exemption, an umbrella's own srcs/hdrs almost
            never `#include` its own re-exported headers (it would be
            self-inclusion), so every umbrella -> sub-target dep would
            be flagged.
        """
        used = set()
        for hdr in all_direct_hdrs:
            used |= self.find_libs_by_header(hdr)
        # Header re-export: any OTHER target that co-owns one of THIS target's
        # own public headers is implicitly "used" -- we're republishing its
        # interface as our own. Use `expanded_hdrs` (this target's own hdrs)
        # NOT `declared_hdrs`, which is the union of self.hdrs and the hdrs
        # of every declared dep -- using that would treat any dep whose hdrs
        # happen to overlap with another dep's hdrs as a re-export, which is
        # not the pattern we want to recognise.
        reexported = set()
        for _hdr, full_hdr in self.expanded_hdrs:
            reexported |= self.find_libs_by_header(full_hdr)
        reexported.discard(self.key)
        candidates = set(self.deps) - used - reexported - self.keep_deps - self.unused_deps_suppress
        candidates.discard(self.key)
        return {dep for dep in candidates
                if not dep.startswith('#:')
                and not self.global_declaration.is_header_less(dep)}

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

        # Track how many files we actually inspect for #includes. If zero,
        # the target has no scannable C/C++ source (e.g. cc_library that
        # only re-exports sub-libraries, cc_flare_library wrapping a .proto
        # whose generated sources live under build_dir, foreign_cc_library
        # consuming a tarball, ...) and an "unused dependency" verdict would
        # be vacuous: blade hasn't seen a single #include from this target.
        # See blade-build#1226.
        scanned_count = [0]  # list to mutate from the closure below

        def check_file(src, full_src):
            if path_under_dir(full_src, self.build_dir):  # Don't check generated files.
                return
            path = self._find_inclusion_file(src)
            if not path:
                console.warning('No inclusion file found for %s' % full_src)
                return
            scanned_count[0] += 1
            direct_hdrs, stacks = _parse_inclusion_stacks(
                path, self.build_dir, self.system_incs)
            # `-H` silently elides direct `#include`s already pulled in by an
            # earlier transitive chain (multiple-include-guard optimization),
            # so supplement the depth-1 set with the source's literal
            # `#include` directives, intersected with paths the compiler
            # actually traversed. The intersection is the gate: dead branches,
            # commented `#include`s, and mis-quoted system headers all drop
            # out because they never reached the compiler. See issue #1171
            # and the design note in `doc/*/develop/hdrs_check.md`.
            scanned = _scan_source_includes(full_src)
            compiled_paths = _read_all_incstk_paths(
                path, self.build_dir, self.system_incs)
            direct_hdrs = list(set(direct_hdrs) | (scanned & compiled_paths))
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
            check_file(src, full_src)

        for hdr, full_hdr in self.expanded_hdrs:
            check_file(hdr, full_hdr)

        severity = self.severity
        if direct_check_msg:
            console.diagnose(self.source_location, severity,
                '{}: Missing dependency declaration:\n{}'.format(self.name, '\n'.join(direct_check_msg)))
        if generated_check_msg:
            console.diagnose(self.source_location, severity,
                '{}: Missing indirect dependency declaration:\n{}'.format(self.name, '\n'.join(generated_check_msg)))

        unused_deps = set()
        # Only run the unused-deps check when we actually scanned at least one
        # source/header for this target. With zero scanned files (umbrella libs,
        # generated-source-only targets, foreign_cc_library wrappers, ...) blade
        # has no #include corpus to compare deps against, so every dep would be
        # flagged "unused" -- always a false positive. See blade-build#1226.
        if self.unused_deps_severity != 'debug' and scanned_count[0] > 0:
            unused_deps = self._check_unused_deps(all_direct_hdrs)
            if unused_deps:
                console.diagnose(self.source_location, self.unused_deps_severity,
                    '{}: Unused dependency (declared in "deps" but none of its public headers is '
                    'directly included):\n{}'.format(
                        self.name, '\n'.join('  ' + self._beautify_lib(d) for d in sorted(unused_deps))))

        ok = (severity != 'error' or not direct_check_msg and not generated_check_msg)
        if self.unused_deps_severity == 'error' and unused_deps:
            ok = False

        details = {}
        if missing_details:
            details['missing_dep'] = missing_details
        if undeclared_hdrs:
            details['undeclared'] = sorted(undeclared_hdrs)
        if unused_deps:
            details['unused_deps'] = sorted(unused_deps)
        details['direct_hdrs'] = all_direct_hdrs
        details['generated_hdrs'] = all_generated_hdrs
        return ok, details


def check(target_check_info_file):
    with open(target_check_info_file, 'rb') as f:
        target = pickle.load(f)
    extra_file = target_check_info_file + '.extra'
    if os.path.exists(extra_file):
        with open(extra_file, 'rb') as f:
            extra_target = pickle.load(f)
        target.update(extra_target)
    checker = Checker(target)
    return checker.check()
