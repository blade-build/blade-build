# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011

# pylint: disable=too-many-lines

"""
This is the cc_target module which is the super class
of all of the cc targets, like cc_library, cc_binary.
"""


import os
import pickle
import sys
from string import Template
from typing import Any

from blade import build_manager
from blade import build_rules
from blade import cc_rule_support
from blade import config  # lgtm[py/cyclic-import]
from blade import console
from blade import inclusion_check
from blade import rule_registry
from blade.blade_types import StrOrListOpt
from blade.constants import HEAP_CHECK_VALUES
from blade.target import Target
from blade.util import (
    mkdir_p,
    path_under_dir,
    run_command,
    stable_unique,
    var_to_list,
    var_to_list_or_none)
from blade.version import LooseVersion as version_parse


# See https://gcc.gnu.org/onlinedocs/gcc/Overall-Options.html#Overall-Options
# _SOURCE_FILE_EXTS is a tuple (not a set) so it fits the Sequence[str] shape
# callers expect; it is only ever consumed as the resolved default for the
# `src_exts=` parameter, and ordering has no semantic effect.
_SOURCE_FILE_EXTS: 'tuple[str, ...]' = ('c', 'cc', 'cp', 'cxx', 'cpp', 'CPP', 'c++', 'C', 's', 'S', 'asm')
# _HEADER_FILE_EXTS stays a set because it is consumed by `in` membership
# checks in :func:`is_header_file`, which benefit from O(1) lookup.
_HEADER_FILE_EXTS = {'h', 'hh', 'H', 'hp', 'hpp', 'hxx', 'HPP', 'h++', 'inc', 'inl', 'tcc'}


def is_header_file(filename):
    """Whether a file is a C/C++ header file."""
    _, ext = os.path.splitext(filename)
    ext = ext[1:]  # Remove leading '.'
    # See https://gcc.gnu.org/onlinedocs/gcc/Overall-Options.html
    return ext in _HEADER_FILE_EXTS


# A dict[hdr, set(target)]
# For a header file, which targets declared it.
_hdr_targets_map = {}

# A dict[inc, set(target)]
# For a include dir, which targets declared it.
_hdr_dir_targets_map = {}


def declare_hdrs(target, hdrs):
    """Declare hdr to lib relationships

    Args:
        target: the target which owns the hdrs
        hdrs:list, the full path (based in workspace troot) of hdrs

    Also registers virtual paths relative to the target's `export_incs`.
    A library that ships its public headers under a private subdirectory
    and exposes them via `-Iexport_inc_path` (e.g. protobuf-3.4.1 with
    `src/google/protobuf/message.h` + `export_incs = ['src']`) needs its
    headers to be reachable both by the full path and by the consumer-
    visible relative path `google/protobuf/message.h`. Without the
    second registration, the unused-deps check can never match
    `#include "google/protobuf/message.h"` back to the owning target,
    and every consumer of such a library gets a spurious "unused
    dependency" notice. See blade-build#1227.
    """
    # Virtual-path registration must consider BOTH export_incs (-I) and
    # system_export_incs (-isystem) -- the include-search-path-relative
    # name is what consumers write in `#include`, irrespective of which
    # flag exposed the search path. Without this, a target with
    # system_include=True (or a ForeignCcLibrary whose export_incs got
    # auto-promoted) would never resolve `#include "foo.h"` back to the
    # owning target, undoing the #1227 fix for system-include targets.
    export_incs = (target.attr.get('export_incs') or []) + (
        target.attr.get('system_export_incs') or [])
    for hdr in hdrs:
        assert not hdr.startswith(target.build_dir)
        hdr = target._source_file_path(hdr)
        if hdr not in _hdr_targets_map:
            _hdr_targets_map[hdr] = set()
        _hdr_targets_map[hdr].add(target.key)
        # Also register the include-search-path-relative form. Use os.sep-
        # normalised comparisons; `_hdr_targets_map` keys are kept as written
        # and normalised on lookup.
        for inc in export_incs:
            prefix = inc.rstrip('/').rstrip(os.sep) + '/'
            if hdr.startswith(prefix):
                rel = hdr[len(prefix):]
                if rel and rel != hdr:
                    if rel not in _hdr_targets_map:
                        _hdr_targets_map[rel] = set()
                    _hdr_targets_map[rel].add(target.key)


def declare_hdr_dir(target, inc):
    """Declare a inc:lib relationship

    Args:
        target: the target which owns the include dir
        inc:str, the full path (based in workspace troot) of include dir
    """
    assert not inc.startswith(target.build_dir), inc
    inc = target._source_file_path(inc)
    if inc not in _hdr_dir_targets_map:
        _hdr_dir_targets_map[inc] = set()
    _hdr_dir_targets_map[inc].add(target.key)


_find_libs_by_header_cache: dict = {}

def find_libs_by_header(hdr):
    result = _find_libs_by_header_cache.get(hdr)
    if result is not None:
        return result
    result = inclusion_check.find_libs_by_header(
                hdr, _hdr_targets_map, _hdr_dir_targets_map)
    _find_libs_by_header_cache[hdr] = result
    return result


# dict(hdr, set(targets))
_private_hdrs_target_map = {}

# set(target_key): libraries declared with an explicit empty `hdrs = []`, i.e.
# "no public interface". Such a lib can never be header-used, so the unused-deps
# check exempts it (flagging it would be pure noise). NOTE: a lib with `hdrs`
# unset (None) is NOT recorded here -- that is a separate `hdrs_missing` warning.
_header_less_target_keys = set()


def declare_private_hdrs(target, hdrs):
    """Declare private header files of a cc target."""
    for h in hdrs:
        hdr = target._source_file_path(h)
        if hdr not in _private_hdrs_target_map:
            _private_hdrs_target_map[hdr] = set()
        _private_hdrs_target_map[hdr].add(target.key)


def declare_header_less(target: 'Target') -> None:
    """Declare a target as having no public headers, exempting it from the
    unused-deps check. Used for cc_libraries with an explicit `hdrs = []` and
    for link-only targets like windows_resources (`.res`, no headers)."""
    _header_less_target_keys.add(target.key)


def inclusion_declaration():
    return {
        'public_hdrs': _hdr_targets_map,
        'public_incs': _hdr_dir_targets_map,
        'private_hdrs': _private_hdrs_target_map,
        'header_less': _header_less_target_keys,
        'allowed_undeclared_hdrs': config.get_item('cc_config', 'allowed_undeclared_hdrs')
    }


def _transitive_declared_generated_includes(target):
    """Collect header/include declarations."""
    attr_key = 'transitive_generated_inludes'
    if attr_key in target.data:
        return target.data[attr_key]

    declared_hdrs = set()
    declared_incs = set()
    build_targets = target.blade.get_build_targets()
    for dkey in target.deps:
        dep = build_targets[dkey]
        for hdr in dep.attr.get('generated_hdrs', []):
            declared_hdrs.add(target._remove_build_dir_prefix(hdr))
        for inc in dep.attr.get('generated_incs', []):
            declared_incs.add(target._remove_build_dir_prefix(inc))
        dep_hdrs, dep_incs = _transitive_declared_generated_includes(dep)
        declared_hdrs.update(dep_hdrs)
        declared_incs.update(dep_incs)
    result = declared_hdrs, declared_incs
    target.data[attr_key] = result
    return result


def _transitive_declared_output_files(target):
    """Collect all files declared as outputs by transitive deps.

    Like ``_transitive_declared_generated_includes`` but also pulls
    ``gen_rule.attr['outputs']``, which lists every file the rule writes
    -- including ``.cc`` / ``.cpp`` source files that wrapper macros
    (e.g. flare's ``cc_flare_library``) feed into a downstream cc_library's
    ``srcs=``. ``generated_hdrs`` alone is insufficient because the
    header-detection filter in gen_rule keeps non-header outputs out of
    that set, but they're still legitimately "generated".

    Used by ``CcTarget._check_hdrs_existence`` (issue #886) to validate
    that any path silently flipped to ``target_file_path(...)`` by
    ``_expand_sources`` is actually going to be produced by something.

    Returns ``(file_set, dir_set)`` of build-dir-stripped paths.
    """
    attr_key = 'transitive_declared_output_files'
    if attr_key in target.data:
        return target.data[attr_key]

    file_set = set()
    dir_set = set()
    build_targets = target.blade.get_build_targets()
    for dkey in target.deps:
        dep = build_targets[dkey]
        for hdr in dep.attr.get('generated_hdrs', []):
            file_set.add(target._remove_build_dir_prefix(hdr))
        for out in dep.attr.get('outputs', []):
            file_set.add(target._remove_build_dir_prefix(out))
        for inc in dep.attr.get('generated_incs', []):
            dir_set.add(target._remove_build_dir_prefix(inc))
        sub_files, sub_dirs = _transitive_declared_output_files(dep)
        file_set |= sub_files
        dir_set |= sub_dirs
    result = file_set, dir_set
    target.data[attr_key] = result
    return result


def is_fission():
    """Whether fission is enabled in cc_config."""
    return config.get_item('cc_config', 'fission')


def need_dwp():
    """Whether dwp is enabled in cc_config."""
    return config.get_item('cc_config', 'dwp')


def _cc_plugin_default_prefix_suffix(toolchain) -> tuple[str, str]:
    """Default (prefix, suffix) for cc_plugin output file names."""
    return (toolchain.lib_prefix, toolchain.dynamic_lib_suffix)


def _windows_dll_basename(path, name):
    """Encode a target's package path + name into a unique DLL base name.

    On Windows a DLL's base name must be unique within the search path (and the
    import lib records it), and DLLs can't be renamed per directory; at test
    time they are flattened into one directory. So the package path is encoded
    into the name, joined by '.' (rarer than '_' in directory names):
    ``//common/net:rpc`` -> ``common.net.rpc.dll``.

    Components are assumed dot-free (target names are identifier-like, and blade
    directories rarely contain '.'); a literal '.' would make the encoding
    ambiguous (``a.b/c`` vs ``a/b.c``), so it is rejected rather than silently
    collided.
    """
    parts = [p for p in path.split('/') if p] + [name]
    bad = [p for p in parts if '.' in p]
    if bad:
        raise ValueError(
            "cannot encode a Windows DLL name: path component(s) %s contain "
            "'.'; rename them or set generate_dynamic=False on this target" % bad)
    return '.'.join(parts) + '.dll'


class CcTarget(Target):
    """
    This class is derived from Target and it is the base class
    of cc_library, cc_binary etc.
    """

    def __init__(self,
                 name: str | None,
                 type: str,
                 srcs: list[str],
                 deps: list[str],
                 visibility: list[str] | None,
                 tags: list[str],
                 warning: str,
                 defs: list[str],
                 incs: list[str],
                 export_incs: list[str],
                 optimize: list[str] | None,
                 linkflags: list[str] | None,
                 extra_cppflags: list[str],
                 extra_linkflags: list[str],
                 kwargs: dict[str, object],
                 extra_cflags: 'StrOrListOpt' = None,
                 extra_cxxflags: 'StrOrListOpt' = None,
                 extra_asflags: 'StrOrListOpt' = None,
                 src_exts: list[str] | None = None,
                 cmd: str = '',
                 system_export_incs: list[str] | None = None):
        """Init method.

        Init the cc target.

        """
        # pylint: disable=too-many-locals
        # Defensive normalization: entry points may pass None as default for
        # these list-ish params (B006 fix). `optimize`/`linkflags` intentionally
        # keep None-sentinel semantics and are handled via var_to_list_or_none.
        defs = var_to_list(defs)
        incs = var_to_list(incs)
        export_incs = var_to_list(export_incs)
        extra_cppflags = var_to_list(extra_cppflags)
        extra_linkflags = var_to_list(extra_linkflags)
        srcs = var_to_list(srcs)
        private_hdrs = [src for src in srcs if is_header_file(src)]
        srcs = [src for src in srcs if not is_header_file(src)]
        deps = var_to_list(deps)
        self.cmd = cmd

        # src_exts=None means "caller did not override" and we fall back to
        # the cc source-extension set. Rule entries that deliberately want an
        # empty extension list (e.g. resource_library, which synthesizes its
        # own .c/.h) should pass src_exts=None explicitly; passing a real list
        # overrides the default (see cu_targets.CuTarget).
        if src_exts is None:
            src_exts = list(_SOURCE_FILE_EXTS)

        super().__init__(
                name=name,
                type=type,
                srcs=srcs,
                src_exts=src_exts,
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)

        self._check_defs(defs)
        self._check_incorrect_no_warning(warning)

        self.attr['warning'] = warning
        self.attr['private_hdrs'] = private_hdrs
        self.attr['defs'] = var_to_list(defs)
        self.attr['incs'] = self._incs_to_fullpath(incs)
        self.attr['export_incs'] = self._incs_to_fullpath(export_incs)
        self.attr['system_export_incs'] = self._incs_to_fullpath(
            var_to_list(system_export_incs))
        self.attr['optimize'] = var_to_list_or_none(optimize)
        self.attr['linkflags'] = var_to_list_or_none(linkflags)
        self.attr['extra_cppflags'] = var_to_list(extra_cppflags)
        self.attr['extra_linkflags'] = var_to_list(extra_linkflags)
        # Per-language extra compile flags (in addition to extra_cppflags, which
        # applies to all C-family sources). Selected per source file by suffix
        # in `_extra_compile_flags_for`. See issue #492.
        self.attr['extra_cflags'] = var_to_list(extra_cflags)
        self.attr['extra_cxxflags'] = var_to_list(extra_cxxflags)
        self.attr['extra_asflags'] = var_to_list(extra_asflags)
        # TODO(chen3feng): Move to CcLibrary
        options = self.blade.get_options()
        self.attr['generate_dynamic'] = (getattr(options, 'generate_dynamic', False) or
                                         config.get_item('cc_library_config', 'generate_dynamic'))
        # `check_undefined` default: CLI override (if --cc-check-undefined or
        # --no-cc-check-undefined was given) wins over the global config.
        # CcLibrary.__init__ then overrides this default if the target sets
        # check_undefined explicitly (tri-state: None inherits this default).
        cli_check_undefined = getattr(options, 'cc_check_undefined', None)
        if cli_check_undefined is not None:
            self.attr['check_undefined'] = cli_check_undefined
        else:
            self.attr['check_undefined'] = config.get_item('cc_library_config', 'check_undefined')
        self.attr['expanded_srcs'] = self._expand_sources(srcs)
        self.attr['expanded_hdrs'] = self._expand_sources(private_hdrs)
        declare_private_hdrs(self, private_hdrs)

    def _expand_sources(self, files):
        """Expand files to [(path, full_path)]."""
        result = []
        for src in files:
            full_path = self._source_file_path(src)
            if not os.path.exists(full_path):
                # Assume generated
                full_path = self._target_file_path(src)
            result.append((src, full_path))
        return result

    def _fullpath_sources(self, files):
        """Expand source files to full_path."""
        result = []
        for src in files:
            full_path = self._source_file_path(src)
            if not os.path.exists(full_path):
                # Assume generated
                full_path = self._target_file_path(src)
            result.append(full_path)
        return result

    def _incs_to_fullpath(self, incs):
        """Expand incs to full path"""
        result = []
        for inc in var_to_list(incs):
            if '..' in inc.split(os.sep):
                self.error('"incs" must not contain "..": %s' % inc)
                continue
            if inc.startswith('//'):  # Full path
                result.append(inc[2:])
            else:
                result.append(os.path.normpath(os.path.join(self.path, inc)))
        return result

    def _set_hdrs(self, hdrs):
        """Set The "hdrs" attribute properly"""
        if hdrs is None:
            suppress = config.get_item('cc_library_config', 'hdrs_missing_suppress')
            if self.key not in suppress:
                severity = config.get_item('cc_library_config', 'hdrs_missing_severity')
                getattr(self, severity)(
                        'Missing "hdrs" declaration. The public header files should be declared '
                        'explicitly, if no public header file, set "hdrs" to empty (hdrs = [])')
            else:
                # The user has intentionally suppressed the hdrs-missing warning for
                # this target, meaning it has no public header for consumers to
                # `#include`. Treat it the same as an explicit `hdrs = []`: the
                # unused-deps check has no possible way to "see" any use of it
                # (its symbols are reached purely at link time, e.g. gtest_main's
                # `main`, protoc's plugin entrypoints), so exempt it. Without
                # this, every consumer of such a target gets a spurious "unused"
                # notice. See blade-build#1228.
                declare_header_less(self)
        elif not hdrs:
            # Explicit `hdrs = []`: the library declares it has no public interface,
            # so the unused-deps check exempts it. See `_header_less_target_keys`.
            declare_header_less(self)
        if not hdrs:
            return
        hdrs = var_to_list(hdrs)
        self._check_sources('header', hdrs, _HEADER_FILE_EXTS)
        declare_hdrs(self, hdrs)
        self.attr['expanded_hdrs'] += self._expand_sources(hdrs)

    __cxx_keyword_list = frozenset([
        'and', 'and_eq', 'alignas', 'alignof', 'asm', 'auto',
        'bitand', 'bitor', 'bool', 'break', 'case', 'catch',
        'char', 'char16_t', 'char32_t', 'class', 'compl', 'const',
        'constexpr', 'const_cast', 'continue', 'decltype', 'default',
        'delete', 'double', 'dynamic_cast', 'else', 'enum',
        'explicit', 'export', 'extern', 'false', 'float', 'for',
        'friend', 'goto', 'if', 'inline', 'int', 'long', 'mutable',
        'namespace', 'new', 'noexcept', 'not', 'not_eq', 'nullptr',
        'operator', 'or', 'or_eq', 'private', 'protected', 'public',
        'register', 'reinterpret_cast', 'return', 'short', 'signed',
        'sizeof', 'static', 'static_assert', 'static_cast', 'struct',
        'switch', 'template', 'this', 'thread_local', 'throw',
        'true', 'try', 'typedef', 'typeid', 'typename', 'union',
        'unsigned', 'using', 'virtual', 'void', 'volatile', 'wchar_t',
        'while', 'xor', 'xor_eq'])

    def _check_defs(self, defs):
        """_check_defs.
        It will warn if user defines c++ keyword in defs list.
        """
        for macro in defs:
            pos = macro.find('=')
            if pos != -1:
                macro = macro[0:pos]
            if macro in CcTarget.__cxx_keyword_list:
                self.warning('DO NOT define c++ keyword "%s" as a macro' % macro)

    def _check_incorrect_no_warning(self, warning):
        """check if warning=no is correctly used or not."""
        srcs = self.srcs
        if not srcs or warning != 'no':
            return

        keywords_list = config.get_item('cc_config', 'no_warning_allowed_paths')
        for keyword in keywords_list:
            if keyword in self.path:
                return

        illegal_path_list = []
        for keyword in keywords_list:
            illegal_path_list += [s for s in srcs if keyword not in s]

        if illegal_path_list:
            self.warning(""""warning='no'" should only be used for thirdparty libraries.""")

    def _check_binary_link_only(self):
        """Check whether a `binary_link_only` library is used correctly"""
        if self.attr.get('binary_link_only'):
            # A binary_link_only library is always allowed to depends on another binary_link_only
            # library
            return
        for dkey in self.deps:
            dep = self.target_database[dkey]
            if dep.attr.get('binary_link_only'):
                self.error('"%s" is a binary_link_only library, can only be a dependent of '
                           'executable target or another binary_link_only library' % dep.fullname)

    def _check_hdrs_existence(self):
        """Diagnose ``hdrs``/``srcs`` entries that exist neither in the source
        tree nor as a declared output of some dep.

        ``_expand_sources`` silently flips any missing source file to
        ``target_file_path(...)`` on the assumption it'll be generated at
        build time. If no dep declares it as an output, the assumption is
        wrong and the path dangles forever -- the typo or missing dep
        surfaces only as a cryptic "file not found" deep in a downstream
        compile, or not at all when nobody happens to include the header.
        Validate up-front. See issue #886.

        Considered "covered" (and skipped):

        * the file exists on disk at the source path (the common case)
        * its build-dir-stripped path matches a declared output of some
          transitive dep:
            * ``generated_hdrs`` (proto / thrift / lex_yacc -- typed header
              generation)
            * ``outputs`` (raw ``gen_rule`` outputs, including ``.cc`` /
              ``.cpp`` source files -- needed for patterns like flare's
              ``cc_flare_library`` macro that wraps a ``gen_rule``-produced
              ``.flare.pb.cc`` into a downstream cc_library)
        * its build-dir-stripped path is under some dep's declared
          ``generated_incs`` directory (e.g. ``thrift_library`` declares
          ``gen-cpp/`` as a generated include root)

        Anything else gets diagnosed at error severity with a hint.
        """
        declared_files, declared_incs = _transitive_declared_output_files(self)
        missing = []
        # Consider both expanded_hdrs and expanded_srcs: a typo'd .cc in
        # srcs has the same silent-flip problem (and while a missing srcs
        # entry usually surfaces later as a compile error, getting the
        # diagnostic at generate time with the BUILD location is strictly
        # better).
        candidates = []
        for entry in self.attr.get('expanded_hdrs', []):
            candidates.append(('header', entry))
        for entry in self.attr.get('expanded_srcs', []):
            candidates.append(('source', entry))
        for kind, (src, full_path) in candidates:
            if not path_under_dir(full_path, self.build_dir):
                continue  # file exists in source tree
            stripped = self._remove_build_dir_prefix(full_path)
            if stripped in declared_files:
                continue  # declared as an output (generated_hdrs or gen_rule outs) by some dep
            if any(path_under_dir(stripped, inc) for inc in declared_incs):
                continue  # under some dep's generated_incs root
            missing.append((kind, src))
        if not missing:
            return
        for kind, src in missing:
            self.error(
                '%s file %r does not exist in the source tree and is not declared '
                'as a generated output by any dep. Did you mistype the filename, '
                'or forget to add the dep that generates it?' % (kind, src))

    def _get_optimize_flags(self):
        """Get optimize flags according to build mode and attributes"""
        optimize = self.attr.get('optimize')
        if optimize is not None:
            optimize = ' '.join(optimize)
        if self.attr.get('always_optimize'):
            return optimize if optimize is not None else '$optimize_flags'
        if self.blade.get_options().profile == 'release':
            return optimize
        return None

    def _get_cc_flags(self):
        """Return ``(cpp_flags, regular_incs, system_incs)``.

        ``regular_incs`` get ``-I``; ``system_incs`` get ``-isystem``. The
        split lets third-party / generated header directories suppress
        their own diagnostics in the consumer's compilation without
        affecting the consumer's first-party include paths.
        """
        cpp_flags = []

        # Defs
        defs = self.attr.get('defs', [])
        cpp_flags += [('-D' + macro) for macro in defs]
        cpp_flags += self.attr.get('extra_cppflags', [])

        # Incs
        regular_incs, system_incs = self._get_incs_list()

        return cpp_flags, regular_incs, system_incs

    def _export_incs_list(self):
        """Return ``(regular_incs, system_incs)`` collected from deps.

        ``system_incs`` come from deps that exported the path via
        ``system_export_incs`` (gen_rule) or ``system_include=True``
        (cc_library) or implicitly (foreign_cc_library). Consumers emit
        ``-isystem`` for those instead of ``-I``, so the dep's own header
        diagnostics don't propagate into the consumer's ``-Werror`` budget.
        """
        regular, system = [], []
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for dep in self.expanded_deps:
            # system dep
            if dep[0] == '#':
                continue
            target = self.target_database[dep]
            regular += target.attr.get('export_incs', [])
            system += target.attr.get('system_export_incs', [])
        return regular, system

    def _get_incs_list(self):
        """Get ``(regular_incs, system_incs)`` for ``-I`` / ``-isystem`` emission.

        Regular: ``attr['incs']`` (private include dirs) + ``attr['export_incs']``
        (advertised to consumers) + transitive non-system ``export_incs`` from deps.

        System: ``attr['system_export_incs']`` (this target's own system-marked
        export dirs) + transitive ``system_export_incs`` from deps.
        """
        own_regular = self.attr.get('incs', []) + self.attr.get('export_incs', [])
        own_system = self.attr.get('system_export_incs', [])
        dep_regular, dep_system = self._export_incs_list()
        # Remove duplicate items in each list while keeping order
        return stable_unique(own_regular + dep_regular), stable_unique(own_system + dep_system)

    def _get_rule_from_suffix(self, src, secret):
        """
        Return cxx for C++ source files with suffix as .cc/.cpp/.cxx,
        return cc otherwise for C, Assembler, etc.
        """
        if secret:
            return 'secretcc'
        for suffix in ('.cc', '.cpp', '.cxx'):
            if src.endswith(suffix):
                return 'cxx'
        # MASM .asm can't go through cl.exe; route to the ml64/ml 'as' rule.
        # (GCC assembles .s/.S via the cc driver, so only MSVC needs this.)
        if src.endswith('.asm') and self.blade.get_build_toolchain().cc_is('msvc'):
            return 'as'
        return 'cc'

    def _extra_compile_flags_for(self, src):
        """Per-source-language extra compile flags (issue #492).

        `extra_cxxflags` for C++ (`.cc`/`.cpp`/`.cxx`, matching the cxx rule
        selection above), `extra_asflags` for assembly (`.s`/`.S`/`.asm`), and
        `extra_cflags` for everything else (C). These are *in addition to*
        `extra_cppflags`, which applies to all C-family sources.
        """
        if src.endswith(('.cc', '.cpp', '.cxx')):
            return self.attr.get('extra_cxxflags', [])
        if src.endswith(('.s', '.S', '.asm')):
            return self.attr.get('extra_asflags', [])
        return self.attr.get('extra_cflags', [])

    def _get_cc_vars(self):
        """Get warning, compile options and include directories for cc build."""
        vars = {}
        # Warnings
        if self.attr.get('warning') != 'yes':
            vars['c_warnings'] = '-w'
            vars['cxx_warnings'] = '-w'

        cppflags, regular_incs, system_incs = self._get_cc_flags()
        if cppflags:
            vars['cppflags'] = ' '.join(cppflags)
        if self.blade.get_build_toolchain().cc_is('msvc'):
            # MSVC: regular incs -> /I; system (3rd-party) incs -> /external:I,
            # the cl.exe analog of GCC's -isystem. The rule also passes
            # /external:W0 so warnings from headers under these dirs are
            # silenced (/external:I alone only tags them). /external is stable
            # since VS2019 16.10.
            inc_flags = (['/I%s' % inc for inc in regular_incs]
                         + ['/external:I "%s"' % inc for inc in system_incs])
        else:
            inc_flags = (['-I%s' % inc for inc in regular_incs]
                         + ['-isystem%s' % inc for inc in system_incs])
        if inc_flags:
            vars['includes'] = ' '.join(inc_flags)

        optimize = self._get_optimize_flags()
        if optimize is not None:
            vars['optimize'] = optimize

        return vars

    def _generate_link_flags(self):
        """Generate linker flags for cc link."""
        linkflags = []
        if 'allow_undefined' in self.attr:
            allow_undefined = self.attr['allow_undefined']
            if not allow_undefined:
                # `-Wl,--no-undefined` is GNU ld syntax. macOS ld64 rejects it,
                # and MSVC does not understand it (LNK4044) — and already errors
                # on unresolved externals by default — so emit it only for the
                # GNU-family linkers that accept it.
                if self.blade.get_build_toolchain().target_os not in ('darwin', 'windows'):
                    linkflags.append('-Wl,--no-undefined')
        return linkflags

    def _generate_link_all_symbols_link_flags(self, libs):
        """Generate link flags for libraries which should be linked with all symbols.

        Platform-aware because the GNU ld spelling
        ``-Wl,--whole-archive ... --no-whole-archive`` is rejected by Apple's
        ld64 / ld-prime with ``ld: unknown option: --whole-archive``. macOS
        uses Mach-O rather than ELF and has no GNU-ld port (Homebrew's
        binutils formula explicitly doesn't install ``ld`` on Darwin), so
        every Mac toolchain — Apple Clang, Homebrew GCC, Homebrew LLVM's
        default driver — eventually hands off to ld64. Emit the Apple
        equivalent ``-Wl,-force_load,<archive>`` once per archive on Darwin
        instead; leave all other platforms (Linux with GNU ld / gold / lld /
        mold, *BSD, etc.) on the original spelling.
        """
        if not libs:
            return []
        if sys.platform == 'darwin':
            return ['-Wl,-force_load,' + lib for lib in libs]
        if os.name == 'nt':
            return ['/WHOLEARCHIVE:' + lib for lib in libs]
        return ['-Wl,--whole-archive'] + libs + ['-Wl,--no-whole-archive']

    def _dynamic_dependencies(self):
        """
        Find dynamic dependencies for ninja build,
        including system libraries and user libraries.
        """
        targets = self.blade.get_build_targets()
        sys_libs, usr_libs = [], []
        incchk_deps = []
        tc = self.blade.get_build_toolchain()
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for key in self.expanded_deps:
            dep = targets[key]
            if dep.path == '#':
                lib_name = getattr(dep, 'libpath', dep.name)
                sys_libs.append(lib_name)
                continue

            lib = dep._get_target_file(tc.DYNAMIC_LIB_LABEL)
            if lib:
                usr_libs.append(lib)
                continue

            # A dependency that opted out of dynamic generation
            # (`generate_dynamic = False`) has no shared library; link its static
            # library into this dynamic_link binary instead. (Like a static build,
            # the dynamic-link path does not apply whole-archive here.)
            static_lib = dep._get_target_file(tc.STATIC_LIB_LABEL)
            if static_lib:
                usr_libs.append(static_lib)
                continue

            # Windows .res files from windows_resources deps (CcInfo-like propagation)
            res_files = dep.data.get('res_files', [])
            if res_files:
                usr_libs.extend(res_files)
                continue

            # '.so' file is not generated for header only libraries, use this file as implicit dep.
            incchk_result = dep._get_target_file('incchk.result')
            if incchk_result:
                incchk_deps.append(incchk_result)

        return sys_libs, usr_libs, incchk_deps

    def _static_dependencies(self):
        """
        Find static dependencies for ninja build, including system libraries
        and user libraries.
        User libraries consist of normal libraries and libraries which should
        be linked all symbols within them using whole-archive option of gnu linker.
        """
        targets = self.blade.get_build_targets()
        sys_libs, usr_libs, link_all_symbols_libs = [], [], []
        incchk_deps = []
        tc = self.blade.get_build_toolchain()
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for key in self.expanded_deps:
            dep = targets[key]
            if dep.path == '#':
                lib_name = getattr(dep, 'libpath', dep.name)
                sys_libs.append(lib_name)
                continue

            lib = dep._get_target_file(tc.STATIC_LIB_LABEL)
            if lib:
                if dep.attr.get('link_all_symbols'):
                    link_all_symbols_libs.append(lib)
                else:
                    usr_libs.append(lib)
                continue

            # Windows .res files from windows_resources deps (CcInfo-like propagation)
            res_files = dep.data.get('res_files', [])
            if res_files:
                usr_libs.extend(res_files)
                continue

            # '.a' file is not generated for header only libraries, use this file as implicit dep.
            incchk_result = dep._get_target_file('incchk.result')
            if incchk_result:
                incchk_deps.append(incchk_result)

        return sys_libs, usr_libs, link_all_symbols_libs, incchk_deps

    def _cc_compile_deps(self):
        """Return a stamp which depends on targets which generate header files."""
        deps = self._collect_cc_compile_deps()
        if len(deps) > 1:
            # If there are more deps, we generate a phony stamp as an alias # to simplify
            # the generated ninja file. For more details, see:
            # https://ninja-build.org/manual.html#_the_literal_phony_literal_rule
            stamp = self._target_file_path(self.name + '__compile_deps__')
            self.generate_build('phony', stamp, inputs=deps, clean=[])
            deps = [stamp]
        return deps

    def _collect_cc_compile_deps(self):
        """Calculate the dependencies for source file compiling.

        If a dependency will generate c/c++ header files, we must depends on it during the
        compiling stage, otherwise, the 'Missing header file' error will occurs.

        Only the generated header files need to be considered. Because the normal header files
        have been covered by the dependency file generated by gcc (the `.d` file) automatically.
        """
        result = set()
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for key in self.expanded_deps:
            dep = self.target_database[key]
            generated_hdrs = dep.attr.get('generated_hdrs')
            if generated_hdrs:
                # NOTE: Here is an optimization: If we know the detaild generated header files,
                # depends on them explicitly rather than depending on the whole target improves
                # the parallelism.
                # For example, if we depends on a proto_library, once its `pb.h` is generated,
                # our source file can be compiled without waiting for its library beeing generated.
                result.update(generated_hdrs)
            elif 'generated_incs' in dep.attr:
                # We know that this target generate header files, but we don't know the details,
                # so we have to depends on its final target file.
                target_file = dep._get_target_file()
                if target_file:
                    result.add(target_file)
            # For any other cases, depends on nothing for compiling.

        return list(result)

    def _cc_objects(self, expanded_srcs, generated_headers=None):
        """Generate cc objects build rules in ninja."""
        vars = self._get_cc_vars()
        # Use `order_only_deps` for generated header files,
        # See https://ninja-build.org/manual.html#ref_dependencies for details.
        order_only_deps = []
        order_only_deps += self._cc_compile_deps()
        if generated_headers and len(generated_headers) > 1:
            order_only_deps += generated_headers

        secret = self.attr.get('secret')

        implicit_deps = []
        if secret:
            implicit_deps.append(self._source_file_path(self.attr['secret_revision_file']))

        objs_dir = self._target_file_path(self.name + '.objs')
        # The compile wrapper writes a `<src>.incstk` inclusion stack (GCC via
        # shell script with -H, MSVC via Python wrapper that tees /showIncludes).
        # The file name is independent of the object suffix, so the rule takes
        # the path via the per-object `inclusion_stack` variable. Declaring it
        # an implicit output (with `restat` on the rule) lets ninja prune the
        # inclusion check when the stack is unchanged. See issue #1161.
        emit_inclusion_stack = self._emits_inclusion_stack()
        objs = []
        inclusion_stacks = []
        for src, full_src in expanded_srcs:
            # secret source is not really exist and is not target of any build, declare it as phony
            # to avoid file missing error
            if secret and path_under_dir(full_src, self.build_dir):
                self.generate_build('phony', full_src, inputs=[], clean=[])
            obj = os.path.join(objs_dir, self.blade.get_build_toolchain().object_file_of(src))
            rule = self._get_rule_from_suffix(src, secret)
            # The ml64/ml 'as' rule does not emit an inclusion stack (assembly
            # is not header-dependency-checked), so don't declare that output.
            emit_stack = emit_inclusion_stack and rule != 'as'
            objvars, stack = vars, None
            extra = self._extra_compile_flags_for(src)
            if emit_stack or extra:
                objvars = dict(vars)
                if emit_stack:
                    stack = os.path.join(objs_dir, src) + '.incstk'
                    objvars['inclusion_stack'] = stack
                if extra:
                    objvars['extra_compile_flags'] = ' '.join(extra)
            self.generate_build(rule, obj, inputs=full_src,
                                implicit_deps=implicit_deps,
                                order_only_deps=order_only_deps,
                                implicit_outputs=[stack] if stack else None,
                                variables=objvars, clean=[])
            objs.append(obj)
            if stack:
                inclusion_stacks.append(stack)
        self._remove_on_clean(objs_dir)

        if 'inclusion_check_info_file' in self.data:
            return objs, self._generate_inclusion_check(
                objs_dir, objs, vars, order_only_deps,
                source_inclusion_stacks=inclusion_stacks if emit_inclusion_stack else None)

        return objs, None

    def _emits_inclusion_stack(self):
        """Whether the cc/cxx compile writes a `<src>.incstk` inclusion stack.

        True for all real compiles (GCC via shell wrapper with -H, MSVC via
        Python wrapper that tees /showIncludes). False for compdb dump where
        the wrapper is bypassed. See issue #1161.
        """
        return not (self.blade.get_command() == 'dump' and
                    getattr(self.blade.get_options(), 'dump_compdb', False))

    def _generated_cc_objects(self, sources, generated_headers=None):
        """Compile generated cc sources"""
        expanded_sources = [(src, self._target_file_path(src)) for src in sources]
        return self._cc_objects(expanded_sources, generated_headers)[0]

    def _generate_inclusion_check(self, objs_dir, objs, vars, order_only_deps,
                                  source_inclusion_stacks=None):
        implicit_deps = []
        # Generate inclusion stack file for header files.
        for hdr, full_hdr in self.attr['expanded_hdrs']:
            if path_under_dir(full_hdr, self.build_dir):  # Don't check generated header files
                continue
            output = os.path.join(objs_dir, hdr) + '.incstk'
            implicit_deps.append(output)
            self.generate_build('cxxhdrs', output, inputs=full_hdr,
                                order_only_deps=order_only_deps, variables=vars, clean=[])
        if source_inclusion_stacks is not None:
            # Each compile declares its `<src>.incstk` as an implicit output
            # (written write-if-changed, with `restat` on the rule). Triggering
            # the check on those instead of the `.o` lets ninja prune it when
            # the inclusion set is unchanged. See issue #1161.
            implicit_deps += source_inclusion_stacks
        else:
            # Fallback (e.g. cuda, or compdb dump where no `.H` is produced): the
            # `.o` is the ordering/trigger dep as before.
            implicit_deps += objs

        check_info_file = self.data['inclusion_check_info_file']
        check_result_file = check_info_file + '.result'
        self.generate_build('ccincchk', outputs=check_result_file, inputs=check_info_file,
                            implicit_deps=implicit_deps)
        self._add_target_file('incchk.result', check_result_file)
        return check_result_file

    def _static_cc_library(self, objs, inclusion_check_result):
        tc = self.blade.get_build_toolchain()
        output = self._target_file_path(tc.static_library_name(self.name))
        self.generate_build('ar', output, inputs=objs,
                            order_only_deps=inclusion_check_result)
        self._add_default_target_file(tc.STATIC_LIB_LABEL, output)
        # `_static_cc_library` is gated by `if objs:` in CcLibrary.generate(),
        # so header-only libs never reach here -- they have no objects, hence
        # no `.a`, no `.syms`, and no undefined-symbol check. Consumers that
        # look up STATIC_LIB_SYMS_LABEL on a header-only dep get None and
        # naturally exclude it from their own check inputs. The guard below
        # is a defensive belt-and-suspenders for any future call path that
        # might land here with an empty `objs`.
        if not objs:
            return
        self._emit_archive_syms(output)
        self._generate_check_undefined(output, inclusion_check_result)

    def _emit_archive_syms(self, archive):
        """Emit a ``ccsyms`` ninja rule that runs ``nm`` on ``archive`` once
        and writes ``<archive>.syms``. The downstream ``ccchkund`` rule reads
        the cache instead of re-running nm.

        On MSVC the archive is a COFF ``.lib`` and the rule reads symbols with
        ``dumpbin`` instead of ``nm`` (wired in the backend); the ``.syms``
        format is identical, so the rest of the check is platform-agnostic.

        Idempotent across multiple call sites: re-registering the same
        STATIC_LIB_SYMS_LABEL on a target is a no-op.
        """
        tc = self.blade.get_build_toolchain()
        if self._get_target_file(tc.STATIC_LIB_SYMS_LABEL):
            return self._get_target_file(tc.STATIC_LIB_SYMS_LABEL)
        syms = archive + '.syms'
        self.generate_build('ccsyms', outputs=syms, inputs=archive)
        self._add_target_file(tc.STATIC_LIB_SYMS_LABEL, syms)
        return syms

    def _generate_check_undefined(self, static_lib, inclusion_check_result):
        """Emit the dep-completeness check rule for this cc_library.

        Skipped when check_undefined is False (per target / CLI / config).

        Works on MSVC too: symbols are read with ``dumpbin`` (``nm`` analog),
        and the ``.obj`` ``/DEFAULTLIB`` directives that pull the CRT outside
        the source-visible ``-l<name>`` graph are covered by the toolchain's
        auto-detected ``default_linked_libs`` baseline (msvcrt / ucrt /
        vcruntime / oldnames), so standard C/C++ symbols don't false-positive.

        Keeps running when generate_dynamic is True as an early, cheaper
        cross-check -- the dynamic link's `-Wl,--no-undefined` is the final
        word, but the static check catches the same misses per-library,
        before any link runs, with faster feedback. See issue #1225.

        Inputs handed to the check tool are all .syms text files:
          1. The target's own ``<archive>.a.syms`` -- both its undefined
             externals (#U section) and its intra-archive defined ones
             (#D section). Produced once per archive by the ``ccsyms``
             rule alongside ``ar``.
          2. Each transitive cc_library dep's ``<archive>.a.syms`` -- same
             format; consumed for the #D set only.
          3. The toolchain's default-linked-libs symbol caches (defined-
             only, pre-generated by BuildManager._prepare_system_symbol_caches).
          4. Per-``#alias`` symbol caches for every system lib declared in
             the target's transitive deps -- which lets the check enforce
             that e.g. ``pow()`` consumers actually declare ``'#m'``.

        This collapses what used to be O(targets × deps) ``nm`` invocations
        (each check re-nm'd every dep's archive) down to one ``nm`` per
        archive total, regardless of how many cc_libraries depend on it.
        """
        if not self.attr.get('check_undefined', True):
            return None
        tc = self.blade.get_build_toolchain()
        # `allow_undefined=True` is the legacy "this library has unresolved
        # symbols by design (the consumer provides them at final link)"
        # signal. It already disables -Wl,--no-undefined at link time; the
        # static check would otherwise contradict it. Per-symbol allowlists
        # (list form) continue through the check below.
        if self.attr.get('allow_undefined') is True:
            return None
        targets = self.blade.get_build_targets()
        dep_syms = []
        system_caches = []
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for key in self.expanded_deps:
            dep = targets[key]
            if dep.path == '#':
                # System library -- e.g. `#pthread`, `#m`, or an absolute-path
                # lib ('#:abslib_<hash>'). Absolute-path libs carry their cache
                # on the SystemLibrary (enumerated from the known path); alias
                # libs resolve theirs via the pre-generated cache map. If no
                # cache exists (resolution failed) skip silently and let the
                # per-target diagnostic surface any genuine miss.
                cache = (getattr(dep, 'syms_cache', None)
                         or self.blade.get_system_symbol_cache(dep.name))
                if cache:
                    system_caches.append(cache)
                continue
            syms = dep._get_target_file(tc.STATIC_LIB_SYMS_LABEL)
            if syms:
                dep_syms.append(syms)
        # Always include the toolchain's default-linked-libs baseline.
        system_caches.extend(self.blade.get_default_linked_system_caches())
        # De-dup (an alias may appear both in defaults and #deps).
        seen = set()
        deduped_caches = []
        for c in system_caches:
            if c not in seen:
                seen.add(c)
                deduped_caches.append(c)
        own_syms = self._get_target_file(tc.STATIC_LIB_SYMS_LABEL)
        if not own_syms:
            # Should have been emitted by _emit_archive_syms() right before
            # this call -- guard anyway so a refactor doesn't silently break
            # the check.
            self.error('cc_check_undefined: %s emitted no .syms; check skipped'
                       % self.fullname)
            return None
        # Materialize the per-target + global allow_undefined patterns into a
        # sidecar file so they survive shell quoting and ninja's variable
        # substitution intact.
        patterns = []
        target_allow = self.attr.get('allow_undefined')
        if isinstance(target_allow, list):
            patterns.extend(target_allow)
        global_allow = config.get_item('cc_library_config', 'allow_undefined')
        if isinstance(global_allow, (list, tuple, set)):
            patterns.extend(global_allow)
        allow_file = static_lib + '.allow'
        # Written at generate time. blade runs with CWD == workspace root, so
        # the relative path resolves correctly both here and in the ninja rule.
        mkdir_p(os.path.dirname(allow_file))
        with open(allow_file, 'w', encoding='utf-8') as f:
            for p in patterns:
                f.write(p)
                f.write('\n')
        # Instead of emitting a per-target ``ccchkund`` ninja rule (which
        # paid one Python-interpreter startup per cc_library on every
        # invocation), accumulate the per-target spec into the build
        # manager. After every target has generated, a single
        # ``ccchkund_batch`` ninja rule fans them all out in one Python
        # process. The check is a no-consumers sidecar (no ninja node
        # depends on the result), so collapsing to one rule has no
        # impact on parallelism with the rest of the build.
        self.blade.register_cc_check_undefined({
            'target_label': '%s:%s' % (self.path, self.name),
            'target_syms': own_syms,
            'dep_syms': dep_syms,
            'sys_caches': deduped_caches,
            'allow_file': allow_file,
        })
        return None

    def _dynamic_cc_library(self, objs, inclusion_check_result):
        tc = self.blade.get_build_toolchain()
        if tc.target_os == 'windows':
            self._dynamic_cc_library_windows(objs, inclusion_check_result, tc)
            return
        output = self._target_file_path(tc.dynamic_library_name(self.name))
        target_linkflags = self._generate_link_flags()
        sys_libs, usr_libs, incchk_deps = self._dynamic_dependencies()
        if inclusion_check_result:
            incchk_deps.append(inclusion_check_result)
        self._cc_link(output, 'solink', objs=objs, deps=usr_libs, sys_libs=sys_libs,
                      version_scripts=self.attr.get('export_map_fullpath'),
                      order_only_deps=incchk_deps, target_linkflags=target_linkflags)
        self._add_target_file(tc.DYNAMIC_LIB_LABEL, output)

    def _dynamic_cc_library_windows(self, objs, inclusion_check_result, tc):
        """Build a Windows DLL: auto-export `.def` -> DLL + import library.

        The DLL is named with its package path encoded in (so DLLs flattened
        into one search dir at test time can't collide and need no per-dir
        rename, which Windows forbids). Dependents link the **import library**
        (`<name>.dll.lib`); `DYNAMIC_LIB_LABEL` therefore points at the import
        lib, while the DLL is recorded separately as the runtime artifact.
        """
        try:
            dll = self._target_file_path(_windows_dll_basename(self.path, self.name))
        except ValueError as e:
            self.error(str(e))
            return
        implib = self._target_file_path(tc.import_library_name(self.name))
        def_file = self._target_file_path(self.name + '.def')
        # Object files -> auto-export `.def` (COMDAT-filtered; see cc_windef).
        # An `export_map` further filters those exports through its version
        # script, matched by demangled name (undname); overloads collapse and
        # quoted signature patterns match by name only -- see cc_windef / #1194.
        export_map = self.attr.get('export_map_fullpath')
        def_vars, def_implicit = None, None
        if export_map:
            def_vars = {'defflags': '--export_map=%s' % export_map[0]}
            def_implicit = [export_map[0]]
        self.generate_build('cc_windef', def_file, inputs=objs,
                            implicit_deps=def_implicit,
                            order_only_deps=inclusion_check_result,
                            variables=def_vars)
        target_linkflags = self._generate_link_flags()
        sys_libs, usr_libs, incchk_deps = self._dynamic_dependencies()
        if inclusion_check_result:
            incchk_deps.append(inclusion_check_result)
        self._cc_link(dll, 'solink', objs=objs, deps=usr_libs, sys_libs=sys_libs,
                      order_only_deps=incchk_deps, target_linkflags=target_linkflags,
                      implicit_deps=[def_file], implicit_outputs=[implib],
                      extra_vars={'dllflags': '/DEF:%s /IMPLIB:%s' % (def_file, implib)})
        # Dependents link the import lib; the DLL is the runtime payload.
        self._add_target_file(tc.DYNAMIC_LIB_LABEL, implib)
        self.data['windows_dll'] = dll

    def _soname_of(self, so_path):
        """Get the `soname` of a shared library."""
        if os.name == 'nt':
            return None  # Windows DLLs don't have ELF-style soname
        returncode, output, unused_stderr = run_command(['objdump', '-p', so_path])
        if returncode != 0:
            return None
        for line in output.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == 'SONAME':
                return parts[1]
        return None

    def _cc_library(self, objs, inclusion_check_result=None):
        self._static_cc_library(objs, inclusion_check_result)
        if self.attr.get('generate_dynamic'):
            self._dynamic_cc_library(objs, inclusion_check_result)

    def _resolve_linker_input_file(self, singular, plural, singular_name, plural_name):
        """Resolve a single linker-input file from the canonical singular
        attribute and its deprecated plural alias.

        Returns the full paths as a list with at most one entry (kept as a
        list so it splices straight into the existing list-shaped
        ``linker_script_fullpath`` / ``export_map_fullpath`` handling and ``_cc_link``).

        Emits a deprecation warning when the plural alias is used, and warns
        when more than one file is given -- a single file is the only
        meaningful count for both a ``--version-script`` export map (GNU ld
        rejects two anonymous version nodes) and a ``-T`` linker script
        (a SECTIONS script replaces the default; multiple conflict).
        """
        files = var_to_list(singular)
        plural_files = var_to_list(plural)
        if plural_files:
            self.warning('"%s" is deprecated, use "%s" (a single file) instead' %
                         (plural_name, singular_name))
            if files:
                self.warning('both "%s" and "%s" are given, "%s" is ignored' %
                             (singular_name, plural_name, plural_name))
            else:
                files = plural_files
        if len(files) > 1:
            self.warning('"%s" expects a single file, but %d were given; '
                         'only the first is used' % (singular_name, len(files)))
            files = files[:1]
        return self._fullpath_sources(files)

    def _cc_link(self, output, rule, objs, deps, sys_libs, linker_scripts=None, version_scripts=None,
                 target_linkflags=None, implicit_deps=None,
                 order_only_deps=None, cmd=None, implicit_outputs=None, extra_vars=None):
        vars = {}
        linkflags = self.attr.get('linkflags')
        if linkflags is not None:
            vars['linkflags'] = ' '.join(linkflags)
        if target_linkflags:
            vars['target_linkflags'] = ' '.join(target_linkflags)
        if cmd:
            vars['cmd'] = cmd
        extra_linkflags = [lib if os.path.isabs(lib) else '-l%s' % lib for lib in sys_libs]
        extra_linkflags += self.attr.get('extra_linkflags')  # pyright: ignore[reportOperatorIssue]
        if implicit_deps is None:
            implicit_deps = []
        # `linker_script` (-T) and `export_map` (--version-script) are GNU-ld
        # spellings. Apple's ld64 understands neither.
        # * linker_script: no native ld64 equivalent. Drop with a warning.
        # * export_map: translate to ld64's -exported_symbols_list by filtering
        #   the objs' symbol table through the version script (same approach
        #   the MSVC path uses to produce a filtered .def). The cc_macos_exports
        #   builtin tool writes a plain mangled-symbol list that ld64 accepts.
        # MSVC has its own export_map path in _dynamic_cc_library_windows and
        # never reaches this branch.
        is_darwin = self.blade.get_build_toolchain().target_os == 'darwin'
        if linker_scripts:
            if is_darwin:
                self.warning(
                    'linker_script is not supported on macOS '
                    '(Apple ld64 lacks the GNU-ld -T option); script ignored')
            else:
                extra_linkflags += ['-T %s' % lds for lds in linker_scripts]
                implicit_deps += linker_scripts
        if version_scripts:
            if is_darwin:
                # GNU ld only ever accepts one anonymous version node, so
                # version_scripts is at most one element here.
                export_map = version_scripts[0]
                exports_list = '%s.exported_symbols_list' % output
                self.generate_build('cc_macos_exports', exports_list,
                                    inputs=objs,
                                    implicit_deps=[export_map],
                                    variables={'export_map': export_map})
                extra_linkflags.append(
                    '-Wl,-exported_symbols_list,' + exports_list)
                implicit_deps.append(exports_list)
            else:
                extra_linkflags += ['-Wl,--version-script=%s' % ver for ver in version_scripts]
                implicit_deps += version_scripts
        if extra_linkflags:
            vars['extra_linkflags'] = ' '.join(extra_linkflags)
        if extra_vars:
            vars.update(extra_vars)
        self.generate_build(rule, output,
                            inputs=objs + deps,
                            implicit_deps=implicit_deps,
                            order_only_deps=order_only_deps,
                            implicit_outputs=implicit_outputs,
                            variables=vars)

    def _write_inclusion_check_info(self):
        """Write a files contains necessary formation for inclusion checking."""
        filename = self._target_file_path(self.name + '.incchk')
        self.data['inclusion_check_info_file'] = filename
        verify_suppress = config.get_item('cc_config', 'hdr_dep_missing_suppress')
        declared_hdrs, declared_incs = self._collect_declared_headers()
        declared_genhdrs, declared_genincs = _transitive_declared_generated_includes(self)
        direct_hdrs, generated_hdrs = self._collect_compiler_reported_hdrs(filename + '.details')

        target_check_info = {
            'type': self.type,
            'name': self.name,
            'cmd': self.cmd,
            'path': self.path,
            'key': self.key,
            'deps': self.deps,
            'build_dir': self.build_dir,
            'source_location': self.source_location,
            'expanded_srcs': self.attr['expanded_srcs'],
            'expanded_hdrs': self.attr['expanded_hdrs'],
            'declared_hdrs': declared_hdrs,
            'declared_incs': declared_incs,
            'declared_genhdrs': declared_genhdrs,
            'declared_genincs': declared_genincs,
            'severity': config.get_item('cc_config', 'hdr_dep_missing_severity'),
            'suppress': verify_suppress.get(self.key, {}),
            'unused_deps_severity': config.get_item('cc_config', 'unused_deps_severity'),
            'unused_deps_suppress':
                config.get_item('cc_config', 'unused_deps_suppress').get(self.key, []),
            'keep_deps': self.attr.get('keep_deps', []),
        }
        content = pickle.dumps(target_check_info)

        # Only update file when content changes to avoid unnecessary recheck
        if os.path.exists(filename):
            if self._incchk_is_valid(filename, content, target_check_info):
                self.debug('Inclusion information no change')
                return
        else:
            mkdir_p(self._target_dir())
        self.debug('Inclusion information updated')
        with open(filename, 'wb') as f:
            f.write(content)

        # Write volatile extra fields to a separate file to avoid unnecessary rebuild.
        #
        # This information is only available after the first build.
        # Therefore, it is empty at the beginning, but is available before the second build.
        # If it is written in the same file as the previous information, unnecessary repeated
        # builds will be triggered.
        # See https://github.com/blade-build/blade-build/issues/1034
        #
        # This information is only a subset of the global file `inclusion_declaration.data` and is
        # passed to the inclusion_check as an optimization to avoid reading the larger global file.
        # So missing this information on the first check is not a problem.
        direct_hdrs, generated_hdrs = self._collect_compiler_reported_hdrs(filename + '.details')
        extra_target_check_info = {
            'hdrs_deps': self._collect_hdrs_deps(direct_hdrs | generated_hdrs),
            'private_hdrs_deps': self._collect_private_hdrs_deps(direct_hdrs),
            'allowed_undeclared_hdrs': self._collect_allowed_undeclared_hdrs(direct_hdrs),
        }
        with open(filename + '.extra', 'wb') as f:
            f.write(pickle.dumps(extra_target_check_info))

    def _incchk_is_valid(self, filename, content, info):
        """Check whether the existing incchk file is still valid."""
        with open(filename, 'rb') as f:
            old_content = f.read()
            # NOTE:
            # Equivalent info may have different pickled length, so we can't depend on
            # the length to optimize the test.
            # if len(old_content) != len(content):  # NO
            #     return False
            if old_content == content:
                return True
            try:
                # The result of pickle is not reproducible for something such as dict
                old_info = pickle.loads(old_content)
                if old_info == info:
                    return True
            except Exception:
                pass
        return False

    def _collect_declared_headers(self):
        """Collect direct headers declarations."""
        declared_hdrs = {full_hdr for hdr, full_hdr in self.attr['expanded_hdrs']}
        declared_incs = set(self.attr.get('generated_incs', []))

        build_targets = self.blade.get_build_targets()
        for key in self.deps:
            dep = build_targets[key]
            for hdr, full_hdr in dep.attr.get('expanded_hdrs', []):
                declared_hdrs.add(self._remove_build_dir_prefix(full_hdr))
            for inc in dep.attr.get('generated_incs', []):
                declared_incs.add(self._remove_build_dir_prefix(inc))
        return declared_hdrs, declared_incs

    def _collect_compiler_reported_hdrs(self, filename):
        """Collect deps for all direct and generated hdrs.

        The information has the following purposes:
        - Trigger recheck when header is newly declared in some targets.
        - When header is checked, search this firstly rather than the larger global
          declaration file (blade_inclusion.data), which is slower.
        """
        if not os.path.exists(filename):
            return set(), set()
        with open(filename, 'rb') as f:
            try:
                details = pickle.load(f)
            except Exception:  # pylint: disable=broad-except
                # Old repr format
                return set(), set()
            return details.get('direct_hdrs', set()), details.get('generated_hdrs', set())

    def _collect_hdrs_deps(self, hdrs):
        result = {}
        for hdr in hdrs:
            result[hdr] = find_libs_by_header(hdr)
        return result

    def _collect_private_hdrs_deps(self, hdrs):
        return {hdr: _private_hdrs_target_map.get(hdr, set()) for hdr in hdrs}

    def _collect_allowed_undeclared_hdrs(self, hdrs):
        allowed = config.get_item('cc_config', 'allowed_undeclared_hdrs')
        return {hdr : hdr in allowed for hdr in hdrs}


class CcLibrary(CcTarget):
    """
    This class is derived from CcTarget and it generates the library
    rules including dynamic library rules according to user option.
    """

    def __init__(self,
                 name: str | None,
                 srcs: StrOrListOpt,
                 hdrs: StrOrListOpt,
                 deps: StrOrListOpt,
                 visibility: StrOrListOpt,
                 tags: StrOrListOpt,
                 warning: str,
                 defs: StrOrListOpt,
                 incs: StrOrListOpt,
                 export_incs: StrOrListOpt,
                 system_include: bool,
                 optimize: StrOrListOpt,
                 always_optimize: bool,
                 link_all_symbols: bool,
                 binary_link_only: bool,
                 deprecated: bool,
                 linkflags: StrOrListOpt,
                 extra_cppflags: StrOrListOpt,
                 extra_cflags: StrOrListOpt,
                 extra_cxxflags: StrOrListOpt,
                 extra_asflags: StrOrListOpt,
                 extra_linkflags: StrOrListOpt,
                 allow_undefined: 'bool | list[str]',
                 secret: bool,
                 secret_revision_file: str | None,
                 generate_dynamic: bool | None,
                 check_undefined: bool | None,
                 export_map: str | None,
                 kwargs: dict[str, object]):
        """Init method.

        Init the cc library.

        """
        # pylint: disable=too-many-locals
        # Normalize list-ish entry params to list[str] once so the forward to
        # super() and the rest of the body can work on a uniform shape.
        # `optimize` / `linkflags` / `visibility` keep None-sentinel semantics.
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        defs = var_to_list(defs)
        incs = var_to_list(incs)
        export_incs = var_to_list(export_incs)
        extra_cppflags = var_to_list(extra_cppflags)
        extra_linkflags = var_to_list(extra_linkflags)
        visibility_list = var_to_list_or_none(visibility)
        optimize_list = var_to_list_or_none(optimize)
        linkflags_list = var_to_list_or_none(linkflags)
        # system_include=True is a convenience that promotes the user's
        # export_incs to system_export_incs (consumers get -isystem instead
        # of -I). Mutually-exclusive in practice: a library either re-exports
        # first-party headers (-I) or third-party / generated headers
        # (-isystem). Setting both is fine; the export_incs branch stays
        # regular and would be the place to add a future system_export_incs
        # parameter for the rare mixed case.
        export_incs_arg, system_export_incs_arg = export_incs, []
        if system_include:
            export_incs_arg, system_export_incs_arg = [], export_incs
        super().__init__(
                name=name,
                type='cc_library',
                srcs=srcs,
                deps=deps,
                visibility=visibility_list,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                export_incs=export_incs_arg,
                system_export_incs=system_export_incs_arg,
                optimize=optimize_list,
                linkflags=linkflags_list,
                extra_cppflags=extra_cppflags,
                extra_cflags=extra_cflags,
                extra_cxxflags=extra_cxxflags,
                extra_asflags=extra_asflags,
                extra_linkflags=extra_linkflags,
                kwargs=kwargs)
        self.attr['link_all_symbols'] = link_all_symbols
        self.attr['binary_link_only'] = binary_link_only
        self.attr['always_optimize'] = always_optimize
        self.attr['deprecated'] = deprecated
        # `allow_undefined` is bool | list[str]:
        #   bool  -> legacy linker control: False emits -Wl,--no-undefined,
        #            True permits any undefined symbol at link time.
        #   list  -> regex patterns whitelisting specific mangled symbols for
        #            the static check_undefined pass. The linker side falls
        #            back to True (allow all) since GNU ld lacks a clean
        #            per-symbol allowlist. See issue #1225.
        self.attr['allow_undefined'] = self._validate_allow_undefined(allow_undefined)
        # `export_map` (a single linker version script) controls which symbols
        # the shared library exports; passed to `--version-script` on Linux when
        # the dynamic library is built (see `_dynamic_cc_library`). No deprecated
        # plural alias here -- `cc_library` never had `version_scripts`.
        self.attr['export_map_fullpath'] = self._resolve_linker_input_file(
            export_map, None, 'export_map', 'version_scripts')
        # `generate_dynamic` is a tri-state: None inherits the global default
        # (already computed in CcTarget.__init__ from --generate-dynamic /
        # cc_library_config.generate_dynamic); an explicit True/False overrides
        # it per target. An explicit False additionally opts the library out of
        # the implicit "generate_dynamic = True" a dynamic_link binary forces on
        # its deps (see Target._expand_deps_generation), so it is always linked
        # statically (the static archive is produced unconditionally).
        if generate_dynamic is not None:
            self.attr['generate_dynamic'] = generate_dynamic
            self.attr['generate_dynamic_forced_off'] = generate_dynamic is False
        # `check_undefined` is tri-state. None inherits the default already
        # computed in CcTarget.__init__ from --[no-]cc-check-undefined /
        # cc_library_config.check_undefined. Explicit True/False overrides.
        if check_undefined is not None:
            self.attr['check_undefined'] = check_undefined
        self._add_tags('lang:cc', 'type:library')
        self._set_secret(secret, secret_revision_file)
        self._set_hdrs(hdrs)

    def _validate_allow_undefined(self, allow_undefined):
        """Normalize and validate the target's allow_undefined attribute.

        Accepts bool (legacy linker control) or list of regex patterns. Lists
        are pre-compiled here to surface invalid regexes at parse time. The
        compiled patterns ride on `attr['allow_undefined_compiled']` so the
        check tool can re-hydrate them without re-parsing.
        """
        if isinstance(allow_undefined, bool):
            return allow_undefined
        if isinstance(allow_undefined, (list, tuple, set)):
            import re as _re
            patterns = list(allow_undefined)
            for p in patterns:
                if not isinstance(p, str):
                    self.error('allow_undefined contains non-string entry: %r' % p)
                    continue
                try:
                    _re.compile(p)
                except _re.error as e:
                    self.error('allow_undefined contains invalid regex %r: %s' % (p, e))
            return patterns
        self.error('allow_undefined must be bool or list[str], got %r' % type(allow_undefined).__name__)
        return False

    def _set_secret(self, secret, secret_revision_file):
        self.attr['secret'] = secret
        if secret and self._check_path(secret_revision_file, 'secret_revision_file'):
            self.attr['secret_revision_file'] = os.path.normpath(secret_revision_file)

    def _before_generate(self):  # override
        """Override"""
        self._write_inclusion_check_info()
        self._check_binary_link_only()
        self._check_hdrs_existence()


    def generate(self):
        """Generate build code for cc object/library."""
        objs, inclusion_check_result = self._cc_objects(self.attr['expanded_srcs'])
        # Don't generate library file for header only library.
        if objs:
            self._cc_library(objs, inclusion_check_result)


class PrebuiltCcLibrary(CcTarget):
    """
    This class describs a prebuilt cc_library target
    """

    def __init__(self,
                 name: str | None,
                 deps: 'StrOrListOpt',
                 hdrs: 'StrOrListOpt',
                 visibility: 'StrOrListOpt',
                 tags: 'StrOrListOpt',
                 export_incs: 'StrOrListOpt',
                 libpath_pattern: str | None,
                 link_all_symbols: bool,
                 binary_link_only: bool,
                 deprecated: bool,
                 kwargs: dict[str, object]):
        """Init method."""
        # pylint: disable=too-many-locals
        # Normalize the BUILD-file-friendly StrOrList unions once, right at
        # the top; everything below (including CcTarget.__init__) sees the
        # layer-2 `list[str]` / `list[str] | None` shape.
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        export_incs = var_to_list(export_incs)
        visibility = var_to_list_or_none(visibility)
        super().__init__(
                name=name,
                type='prebuilt_cc_library',
                srcs=[],
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning='no',
                defs=[],
                incs=[],
                export_incs=export_incs,
                optimize=None,
                linkflags=None,
                extra_cppflags=[],
                extra_linkflags=[],
                kwargs=kwargs)
        self.attr['libpath_pattern'] = libpath_pattern
        self.attr['link_all_symbols'] = link_all_symbols
        self.attr['binary_link_only'] = binary_link_only
        self.attr['deprecated'] = deprecated
        self._add_tags('lang:cc', 'type:library', 'type:prebuilt')
        self._set_hdrs(hdrs)
        self._setup()

    def _setup(self):
        # There are 3 cases for prebuilt library as below:
        #   1. Only static library(.a) exists
        #   2. Only dynamic library(.so) exists
        #   3. Both static and dynamic libraries exist
        # If there is only one kind of library, we have to use it any way.
        # But in the third case, we use static library for static linking,
        # and use dynamic library for dynamic linking.
        tc = self.blade.get_build_toolchain()
        static_source = self._library_source_path(tc.static_lib_suffix)
        dynamic_source = self._library_source_path(tc.dynamic_lib_suffix)
        has_static = os.path.exists(static_source)
        has_dynamic = os.path.exists(dynamic_source)

        if not has_static and not has_dynamic:
            self.error(f'Can not find either {static_source} or {dynamic_source}')
            return

        if has_static:
            self.attr['static_source'] = static_source
            self._add_target_file(tc.STATIC_LIB_LABEL, static_source)
            if not has_dynamic:
                # Using static library for dynamic linking
                self._add_target_file(tc.DYNAMIC_LIB_LABEL, static_source)

        if has_dynamic:
            dynamic_target = self._target_file_path(os.path.basename(dynamic_source))
            self.attr['dynamic_source'] = dynamic_source
            self.attr['dynamic_target'] = dynamic_target
            self._add_target_file(tc.DYNAMIC_LIB_LABEL, dynamic_target)

            soname = self._soname_of(dynamic_source)
            if soname:
                self.data['soname_and_full_path'] = (soname, dynamic_target)

            if not has_static:
                # Using dynamic library for static linking
                self._add_target_file(tc.STATIC_LIB_LABEL, dynamic_target)

    _default_libpath = None

    def _library_source_path(self, suffix):
        """Library full path in source dir"""
        options = self.blade.get_options()
        bits, arch, profile = options.bits, options.arch, options.profile
        if PrebuiltCcLibrary._default_libpath is None:
            pattern = config.get_item('cc_library_config', 'prebuilt_libpath_pattern')
            PrebuiltCcLibrary._default_libpath = Template(pattern).substitute(
                bits=bits, arch=arch, profile=profile)

        pattern = self.attr.get('libpath_pattern')
        if pattern is None:
            libpath = PrebuiltCcLibrary._default_libpath
        else:
            libpath = Template(pattern).substitute(bits=bits,
                                                   arch=arch,
                                                   profile=profile)

        libpath = os.path.join(self.path, libpath)

        tc = self.blade.get_build_toolchain()
        return os.path.join(libpath, f'{tc.lib_prefix}{self.name}{suffix}')

    def _is_depended_on(self):
        """Whether this library is actually depended on by any target."""
        build_targets = self.blade.get_build_targets()
        for key in self.expanded_dependents:
            t = build_targets[key]
            if t.type != 'prebuilt_cc_library':
                return True
        return False

    def _rpath_link(self, dynamic):
        path = self._library_source_path(
            self.blade.get_build_toolchain().dynamic_lib_suffix)
        if os.path.exists(path):
            return os.path.dirname(path)
        return None

    def soname_and_full_path(self):
        """Return soname and full path of the shared library, if any"""
        # When a prebuilt shared library with a 'soname' is linked into a program
        # Its name appears in the program's DT_NEEDED tag without full path.
        # So we need to make a symbolic link let the program find the library.
        return self.data.get('soname_and_full_path')

    def _before_generate(self):  # override
        """Override"""
        self._write_inclusion_check_info()
        self._check_binary_link_only()
        # Deliberately not calling _check_hdrs_existence here: a
        # prebuilt_cc_library's hdrs are descriptive ("these are the
        # headers consumers will #include"), and the .h files typically
        # live in an external prebuilt installation root (configured via
        # `libpath_pattern` + `prebuilt_libpath_pattern`), not the
        # workspace source tree. The missing-file check would false-
        # positive on every well-formed prebuilt declaration.

    def generate(self):
        """Generate build code for cc object/library."""
        # We allow a prebuilt cc_library doesn't exist if it is not used.
        # So if this library is not depended on by any target, don't generate any
        # rule to avoid runtime error and also avoid unnecessary runtime cost.
        if not self._is_depended_on():
            return
        objs, inclusion_check_result = self._cc_objects([])
        # Emit ``ccsyms`` for the prebuilt static archive when present. Has to
        # happen here in generate() rather than _setup() because _setup() runs
        # at BUILD-loading time and emitting a build rule that early forces
        # __build_code initialization, which breaks the
        # ``assert __build_code is None`` invariant in ``before_generate``.
        static_source = self.attr.get('static_source')
        if static_source:
            self._emit_archive_syms(static_source)
        dynamic_source = self.attr.get('dynamic_source')
        dynamic_target = self.attr.get('dynamic_target')
        if dynamic_source and dynamic_target:
            self.generate_build('copy', dynamic_target, inputs=dynamic_source,
                                order_only_deps=inclusion_check_result)


class VcpkgLibrary(PrebuiltCcLibrary):
    """A library resolved from a vcpkg install tree (issue #1236).

    Auto-created by the vcpkg dependency provider (NOT declared in a BUILD
    file) for a `vcpkg#<port>:<lib>` reference -- the same lifecycle as a
    SystemLibrary. It wraps a pre-existing static archive under
    `<root>/installed/<triplet>/lib/` plus the install tree's include dir;
    `vcpkg#<port>:hdrs` is a header-only port (include dir only, no archive).

    The backing `.a` lives outside the build tree, so `_setup` is overridden to
    look at the resolved absolute path directly rather than the source-relative
    path PrebuiltCcLibrary computes.
    """

    def __init__(self, port, lib, key, lib_dir, include_dir, header_only):
        # Stash the vcpkg-resolved locations before super().__init__, which
        # calls our _setup() at the end of construction.
        self._vcpkg_port = port
        self._vcpkg_lib_dir = lib_dir
        self._vcpkg_header_only = header_only
        super().__init__(
                name=lib,
                deps=[],
                hdrs=[],
                visibility=['PUBLIC'],
                tags=['lang:cc', 'type:library', 'type:vcpkg'],
                export_incs=[],
                libpath_pattern=None,
                link_all_symbols=False,
                binary_link_only=False,
                deprecated=False,
                kwargs={})
        # Re-key as the canonical provider reference. The path sentinel must not
        # be '#' -- that marks a `-l` system lib in the link/incs resolution.
        # Done before declare_hdr_dir below so the headers register under the
        # final key.
        self.type = 'vcpkg_library'
        self.path = 'vcpkg#' + port
        self.key = key
        self.fullname = '//' + key
        # Target.__init__ derived target_dir from the *referrer's* source path
        # (the BUILD file that first named this lib). That collides with the
        # referrer's own outputs when it is e.g. a //thirdparty/<port> wrapper
        # named after the lib. Redirect this auto-created target's outputs to a
        # unique per-(port, lib) dir under the build tree.
        self.target_dir = os.path.normpath(os.path.join(
            self.build_dir, '.cache', 'vcpkg', 'targets', port, lib))
        if include_dir:
            # External headers go via -isystem so third-party warnings don't
            # trip the consumer's -Werror (same posture as foreign_cc_library);
            # absolute paths survive _incs_to_fullpath unchanged.
            self.attr['system_export_incs'] = self._incs_to_fullpath([include_dir])
        # Exempt from the unused-deps check: vcpkg headers live in an absolute,
        # out-of-tree `-isystem` dir, which blade's inclusion scanner can't
        # attribute back to this target (declare_hdr_dir works only for
        # in-tree dirs). Flagging every vcpkg dep as "unused" would be pure
        # noise; precise external-header attribution is a follow-up.
        declare_header_less(self)

    def _setup(self):  # override PrebuiltCcLibrary._setup
        tc = self.blade.get_build_toolchain()
        if self._vcpkg_header_only:
            return
        archive = os.path.join(
            self._vcpkg_lib_dir,
            f'{tc.lib_prefix}{self.name}{tc.static_lib_suffix}')
        if not os.path.exists(archive):
            self.error(
                'vcpkg#%s:%s: static library not found at %s; run '
                '`vcpkg install %s` for this triplet' % (
                    self._vcpkg_port, self.name, archive, self._vcpkg_port))
            return
        self.attr['static_source'] = archive
        self._add_target_file(tc.STATIC_LIB_LABEL, archive)
        # No separate shared lib is resolved in this phase; the static archive
        # serves both link modes (consumers that dynamic_link still get it).
        self._add_target_file(tc.DYNAMIC_LIB_LABEL, archive)

    def generate(self):  # override
        # The static archive + include dir are pure metadata resolved in
        # _setup(); there is nothing to build. Emit archive-syms (for the
        # cc_check_undefined static check) only when the archive lives under the
        # build dir -- i.e. blade-managed installs. For an unmanaged tree the
        # `.syms` would land in the user's shared $VCPKG_ROOT, so skip it there.
        static = self.attr.get('static_source')
        if static and static.startswith(os.path.abspath(self.build_dir) + os.sep):
            self._emit_archive_syms(static)


def prebuilt_cc_library(
        name: str,
        deps: 'StrOrListOpt' = None,
        visibility: 'StrOrListOpt' = None,
        tags: 'StrOrListOpt' = None,
        export_incs: 'StrOrListOpt' = None,
        hdrs: 'StrOrListOpt' = None,
        libpath_pattern: str | None = None,
        link_all_symbols: bool = False,
        binary_link_only: bool = False,
        deprecated: bool = False,
        **kwargs: object):
    """prebuilt_cc_library rule"""
    target = PrebuiltCcLibrary(
            name=name,
            deps=deps,
            visibility=visibility,
            tags=tags,
            export_incs=export_incs,
            hdrs=hdrs,
            libpath_pattern=libpath_pattern,
            link_all_symbols=link_all_symbols,
            binary_link_only=binary_link_only,
            deprecated=deprecated,
            kwargs=kwargs)
    build_manager.instance.register_target(target)
    return target


def cc_library(
        name: str,
        srcs: StrOrListOpt = None,
        hdrs: StrOrListOpt = None,
        deps: StrOrListOpt = None,
        keep_deps: StrOrListOpt = None,
        visibility: StrOrListOpt = None,
        tags: StrOrListOpt = None,
        warning: str = 'yes',
        defs: StrOrListOpt = None,
        incs: StrOrListOpt = None,
        export_incs: StrOrListOpt = None,
        system_include: bool = False,
        optimize: StrOrListOpt = None,
        always_optimize: bool = False,
        pre_build: bool = False,
        prebuilt: bool = False,
        prebuilt_libpath_pattern: str | None = None,
        link_all_symbols: bool = False,
        binary_link_only: bool = False,
        deprecated: bool = False,
        linkflags: StrOrListOpt = None,
        extra_cppflags: StrOrListOpt = None,
        extra_cflags: StrOrListOpt = None,
        extra_cxxflags: StrOrListOpt = None,
        extra_asflags: StrOrListOpt = None,
        extra_linkflags: StrOrListOpt = None,
        allow_undefined: 'bool | list[str]' = False,
        secret: bool = False,
        secret_revision_file: str | None = None,
        secure: bool = False,
        generate_dynamic: bool | None = None,
        check_undefined: bool | None = None,
        export_map: str | None = None,
        **kwargs: object):
    """cc_library target.

    Args:
        secret: bool, Whether this library is a recret library.
            For confidential libraries, the source code may not exist locally, and remote
            compilation needs to be initiated through a confidential compiler.
            Authorized developers can checkout the source code to a certain subdirectory.
        secret_revision_file: str, revision file for secret compiling.
            Blade does not understand its content, only uses it to represent a certain version of
            the remote source code. When the version changes, the file should be updated to
            trigger recompilation.
    """
    # pylint: disable=too-many-locals
    # `keep_deps` are real deps (built/linked/header-visible) merged into `deps`,
    # but recorded so the unused-deps check exempts them. See issue #1155.
    keep_deps = var_to_list(keep_deps)
    deps = var_to_list(deps) + keep_deps
    if pre_build or prebuilt:
        target = prebuilt_cc_library(
                name=name,
                hdrs=hdrs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                export_incs=export_incs,
                libpath_pattern=prebuilt_libpath_pattern,
                link_all_symbols=link_all_symbols,
                binary_link_only=binary_link_only,
                deprecated=deprecated,
                **kwargs)
        # target.warning('"cc_library.prebuilt" is deprecated, please use the standalone '
        #                '"prebuilt_cc_library" rule')
        return
    target = CcLibrary(
            name=name,
            srcs=srcs,
            hdrs=hdrs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            defs=defs,
            incs=incs,
            export_incs=export_incs,
            system_include=system_include,
            optimize=optimize,
            always_optimize=always_optimize,
            link_all_symbols=link_all_symbols,
            binary_link_only=binary_link_only,
            deprecated=deprecated,
            linkflags=linkflags,
            extra_cppflags=extra_cppflags,
            extra_cflags=extra_cflags,
            extra_cxxflags=extra_cxxflags,
            extra_asflags=extra_asflags,
            extra_linkflags=extra_linkflags,
            allow_undefined=allow_undefined,
            secret=secret or secure,
            secret_revision_file=secret_revision_file,
            generate_dynamic=generate_dynamic,
            check_undefined=check_undefined,
            export_map=export_map,
            kwargs=kwargs)
    target.attr['keep_deps'] = [target._unify_dep(d) for d in keep_deps]
    build_manager.instance.register_target(target)


class ForeignCcLibrary(CcTarget):
    """
    This class describs a foreign cc_library target
    """

    def __init__(self,
                 name: str | None,
                 deps: 'StrOrListOpt',
                 install_dir: str,
                 hdrs: 'StrOrListOpt',
                 hdr_dir: str,
                 visibility: 'StrOrListOpt',
                 tags: 'StrOrListOpt',
                 export_incs: 'StrOrListOpt',
                 lib_dir: str,
                 has_dynamic: bool,
                 link_all_symbols: bool,
                 binary_link_only: bool,
                 deprecated: bool,
                 kwargs: dict[str, object]):
        """Init method."""
        # pylint: disable=too-many-locals
        # Normalize the BUILD-file-friendly StrOrList unions once, right at
        # the top; everything below (including CcTarget.__init__ and the
        # hdrs-branch further down) sees layer-2 `list[str]` /
        # `list[str] | None`.
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        export_incs = var_to_list(export_incs)
        hdrs = var_to_list(hdrs)
        visibility = var_to_list_or_none(visibility)
        # ForeignCcLibrary is by definition a wrapper around external code; its
        # headers' diagnostics aren't the consumer's concern. Promote any
        # user-supplied `export_incs` to `system_export_incs` so consumers see
        # `-isystem` instead of `-I` -- gcc/clang suppress warnings raised
        # inside system headers under `-Werror`. Equivalent in spirit to
        # Bazel's rules_foreign_cc, which marks its include outputs as
        # `cc_library(includes=...)` rather than `strip_include_prefix`.
        super().__init__(
                name=name,
                type='foreign_cc_library',
                srcs=[],
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning='no',
                defs=[],
                incs=[],
                export_incs=[],
                system_export_incs=export_incs,
                optimize=None,
                linkflags=None,
                extra_cppflags=[],
                extra_linkflags=[],
                kwargs=kwargs)
        self.attr['install_dir'] = install_dir
        self.attr['link_all_symbols'] = link_all_symbols
        self.attr['deprecated'] = deprecated
        self.attr['lib_dir'] = lib_dir
        self.attr['has_dynamic'] = has_dynamic
        self._add_tags('lang:cc', 'type:library', 'type:foreign')

        if hdrs:
            hdrs = [os.path.join(install_dir, h) for h in hdrs]
            declare_hdrs(self, hdrs)
            hdrs = [self._target_file_path(os.path.join(install_dir, h)) for h in hdrs]
            self.attr['generated_hdrs'] = hdrs
        else:
            hdr_dir = os.path.join(install_dir, hdr_dir)
            declare_hdr_dir(self, hdr_dir)
            hdr_dir = self._target_file_path(hdr_dir)
            self.attr['generated_incs'] = [hdr_dir]
            # The hdr_dir we just registered is the *source-tree* layout of the
            # foreign package (e.g. `thirdparty/gflags/gflags`), but consumers
            # only ever #include from the *installed* layout via `-I<build>/...
            # /include` (e.g. `#include <gflags/gflags.h>`). `find_libs_by_header`
            # walks up directories starting at the include string, so the source
            # path it stored will never match, and every consumer of a
            # foreign_cc_library that didn't enumerate explicit `hdrs` would get
            # spurious "unused dependency" notices. Treat such targets as
            # header-less for the unused-deps check, mirroring the behaviour of
            # `hdrs = []` and the implicit-no-hdrs branch in `_set_hdrs`. See
            # blade-build#1228.
            declare_header_less(self)

    def _library_full_path(self, suffix):
        """Return full path of the library file with specified suffix"""
        tc = self.blade.get_build_toolchain()
        assert suffix in tc.all_dynamic_lib_suffixes + (tc.static_lib_suffix,), suffix
        return self._target_file_path(os.path.join(
            self.attr['install_dir'], self.attr['lib_dir'],
            f'{tc.lib_prefix}{self.name}{suffix}'))

    def soname_and_full_path(self):
        """Return soname and full path of the shared library, if any"""
        if 'soname_and_full_path' not in self.data:
            self.data['soname_and_full_path'] = None
            if self.attr['has_dynamic']:
                tc = self.blade.get_build_toolchain()
                so_path = self._library_full_path(tc.dynamic_lib_suffix)
                soname = self._soname_of(so_path)
                if soname:
                    self.data['soname_and_full_path'] = (soname, so_path)
        return self.data['soname_and_full_path']

    def _before_generate(self):  # override
        """Override"""
        self._write_inclusion_check_info()
        self._check_binary_link_only()
        self._check_hdrs_existence()

    def _ninja_rules(self):
        tc = self.blade.get_build_toolchain()
        a_path = self._library_full_path(tc.static_lib_suffix)
        so_path = self._library_full_path(tc.dynamic_lib_suffix)
        self._add_default_target_file(tc.STATIC_LIB_LABEL, a_path)
        self._emit_archive_syms(a_path)
        self._add_target_file(tc.DYNAMIC_LIB_LABEL,
                              so_path if self.attr['has_dynamic'] else a_path)

    def generate(self):
        """Generate build code for cc object/library."""
        self._ninja_rules()


def foreign_cc_library(
        name: str | None = None,
        install_dir: str = '',
        lib_dir: str = 'lib',
        hdrs: 'StrOrListOpt' = None,
        hdr_dir: str = '',
        export_incs: 'StrOrListOpt' = None,
        deps: 'StrOrListOpt' = None,
        has_dynamic: bool = False,
        link_all_symbols: bool = False,
        binary_link_only: bool = False,
        visibility: 'StrOrListOpt' = None,
        tags: 'StrOrListOpt' = None,
        deprecated: bool = False,
        **kwargs: object):
    """Similar to a prebuilt cc_library, but it is built by a foreign build system,
    such as autotools, cmake, etc.

    Args:
        install_dir: str, the name of the directory where the package is installed,
            relative to the output directory
        hdrs: header files to be declared, always under the output directory
        hdr_dir: header file directory to be declared, always under the output directory
        lib_dir: str, the relative path of the lib dir under the `install_dir` dir.
        has_dynamic: bool, whether this library has a dynamic edition.
    """
    target = ForeignCcLibrary(
            name=name,
            deps=deps,
            visibility=visibility,
            tags=tags,
            export_incs=export_incs,
            install_dir=install_dir,
            hdrs=hdrs,
            hdr_dir=hdr_dir,
            lib_dir=lib_dir,
            has_dynamic=has_dynamic,
            link_all_symbols=link_all_symbols,
            binary_link_only=binary_link_only,
            deprecated=deprecated,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(cc_library)
build_rules.register_function(foreign_cc_library)
build_rules.register_function(prebuilt_cc_library)


class CcBinary(CcTarget):
    """
    This class is derived from CcTarget and it generates the cc_binary
    rules according to user options.
    """

    is_executable = True  # also covers CcTest

    def __init__(self,
                 name: str | None,
                 srcs: StrOrListOpt,
                 deps: StrOrListOpt,
                 visibility: StrOrListOpt,
                 tags: StrOrListOpt,
                 warning: str,
                 defs: StrOrListOpt,
                 incs: StrOrListOpt,
                 embed_version: bool,
                 optimize: StrOrListOpt,
                 dynamic_link: bool,
                 linkflags: StrOrListOpt,
                 extra_cppflags: StrOrListOpt,
                 extra_cflags: StrOrListOpt,
                 extra_cxxflags: StrOrListOpt,
                 extra_asflags: StrOrListOpt,
                 extra_linkflags: StrOrListOpt,
                 linker_script: str | None,
                 linker_scripts: StrOrListOpt,
                 export_map: str | None,
                 version_scripts: StrOrListOpt,
                 export_dynamic: bool,
                 kwargs: dict[str, object]):
        """Init method.

        Init the cc binary.

        """
        # pylint: disable=too-many-locals
        # Normalize list-ish entry params to list[str] once so the forward to
        # super() and the rest of the body can work on a uniform shape.
        # `optimize` / `linkflags` / `visibility` keep None-sentinel semantics.
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        defs = var_to_list(defs)
        incs = var_to_list(incs)
        extra_cppflags = var_to_list(extra_cppflags)
        extra_linkflags = var_to_list(extra_linkflags)
        visibility_list = var_to_list_or_none(visibility)
        optimize_list = var_to_list_or_none(optimize)
        linkflags_list = var_to_list_or_none(linkflags)
        super().__init__(
                name=name,
                type='cc_binary',
                srcs=srcs,
                deps=deps,
                visibility=visibility_list,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                export_incs=[],
                optimize=optimize_list,
                linkflags=linkflags_list,
                extra_cppflags=extra_cppflags,
                extra_cflags=extra_cflags,
                extra_cxxflags=extra_cxxflags,
                extra_asflags=extra_asflags,
                extra_linkflags=extra_linkflags,
                kwargs=kwargs)
        self.attr['embed_version'] = embed_version
        self.attr['dynamic_link'] = dynamic_link
        self.attr['linker_script_fullpath'] = self._resolve_linker_input_file(
            linker_script, linker_scripts, 'linker_script', 'linker_scripts')
        self.attr['export_map_fullpath'] = self._resolve_linker_input_file(
            export_map, version_scripts, 'export_map', 'version_scripts')
        self.attr['export_dynamic'] = export_dynamic
        self.attr['dwp'] = is_fission() and need_dwp()
        self._add_tags('lang:cc', 'type:binary')

        # add extra link library
        link_libs = var_to_list(config.get_item('cc_binary_config', 'extra_libs'))
        self._add_implicit_library(link_libs)

    def _allow_duplicate_source(self):
        return True

    def _expand_deps_generation(self):
        if self.attr.get('dynamic_link'):
            build_targets = self.blade.get_build_targets()
            assert self.expanded_deps is not None, 'expanded_deps not expanded'
            for dep in self.expanded_deps:
                # Respect a library's explicit `generate_dynamic = False`: such a
                # dep is never built as a shared library and is linked statically
                # even into a dynamic_link binary.
                if build_targets[dep].attr.get('generate_dynamic_forced_off'):
                    continue
                build_targets[dep].attr['generate_dynamic'] = True

    def _get_rpath_links(self):
        """Get rpath_links from dependencies"""
        dynamic_link = self.attr['dynamic_link']
        build_targets = self.blade.get_build_targets()
        rpath_links = []
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for lib in self.expanded_deps:
            if build_targets[lib].type == 'prebuilt_cc_library':
                path = build_targets[lib]._rpath_link(dynamic_link)
                if path and path not in rpath_links:
                    rpath_links.append(path)

        return rpath_links

    def _generate_cc_binary_link_flags(self, dynamic_link):
        linkflags = []
        toolchain = self.blade.get_build_toolchain()
        if (not dynamic_link and toolchain.cc_is('gcc')
                and version_parse(toolchain.get_cc_version()) > version_parse('4.5')
                and sys.platform != 'darwin'):
            linkflags += ['-static-libgcc', '-static-libstdc++']
        if self.attr.get('export_dynamic'):
            # `-rdynamic` is a GNU-ld / ld64 (ELF/Mach-O) flag. MSVC link.exe
            # has no equivalent -- it just answers LNK4044 and ignores it -- so
            # don't emit it there; warn that the option has no effect instead of
            # leaking a bogus flag. Explicit exe symbol export on Windows is
            # tracked in #1201.
            if toolchain.cc_is('msvc'):
                self.warning(
                    'export_dynamic has no effect on the MSVC toolchain; an '
                    'executable does not export its symbols. Export them '
                    'explicitly with /EXPORT linker options (linkflags) or a '
                    '.def file. See issue #1201.')
            else:
                linkflags.append('-rdynamic')
        linkflags += self._generate_link_flags()
        for rpath_link in self._get_rpath_links():
            linkflags.append('-Wl,--rpath-link=%s' % rpath_link)
        return linkflags

    def _cc_binary(self, objs, inclusion_check_result, dynamic_link):
        implicit_deps = None
        target_linkflags = self._generate_cc_binary_link_flags(dynamic_link)
        if dynamic_link:
            sys_libs, usr_libs, incchk_deps = self._dynamic_dependencies()
        else:
            sys_libs, usr_libs, link_all_symbols_libs, incchk_deps = self._static_dependencies()
            if link_all_symbols_libs:
                target_linkflags += self._generate_link_all_symbols_link_flags(link_all_symbols_libs)
                implicit_deps = link_all_symbols_libs

        # Using incchk as order_only_deps to avoid relink when only inclusion check is done.
        order_only_deps = incchk_deps
        if inclusion_check_result:
            order_only_deps.append(inclusion_check_result)

        if self.attr['embed_version']:
            scm = self.blade.get_build_toolchain().object_file_of(
                os.path.join(self.build_dir, 'scm.cc'))
            objs.append(scm)
            order_only_deps.append(scm)
        output = self._target_file_path(
            self.blade.get_build_toolchain().executable_file_name(self.name))
        self._cc_link(output, 'link', objs=objs, deps=usr_libs, sys_libs=sys_libs,
                      linker_scripts=self.attr.get('linker_script_fullpath'),
                      version_scripts=self.attr.get('export_map_fullpath'),
                      target_linkflags=target_linkflags,
                      implicit_deps=implicit_deps,
                      order_only_deps=order_only_deps)
        self._add_default_target_file('bin', output)
        self._remove_on_clean(self._target_file_path(self.name + '.runfiles'))
        if is_fission() and self.attr.get("dwp"):
            self._generate_dwp(output, objs, implicit_deps, order_only_deps)


    def _generate_dwp(self, binary_path, objs, implicit_deps, order_only_deps):
        """Generate dwp file."""
        if not is_fission():
            return
        if not self.blade.get_build_toolchain().cc_is('gcc'):
            console.warning('fission/dwp is not supported on this toolchain, skipping')
            return

        _, usr_libs, link_all_symbols_libs, _ = self._static_dependencies()

        dwp_inputs = objs + usr_libs + link_all_symbols_libs
        dwp_output = binary_path + '.dwp'

        self.generate_build('dwp', dwp_output,
                            inputs=dwp_inputs,
                            implicit_deps=implicit_deps,
                            order_only_deps=order_only_deps)
        self._add_target_file('dwp', dwp_output)

    def _before_generate(self):  # override
        """Override"""
        self._write_inclusion_check_info()
        self._check_hdrs_existence()

    def generate(self):
        """Generate build code for cc binary/test."""
        objs, inclusion_check_result = self._cc_objects(self.attr['expanded_srcs'])
        self._cc_binary(objs, inclusion_check_result, self.attr['dynamic_link'])


def cc_binary(name: str,
              srcs: StrOrListOpt = None,
              deps: StrOrListOpt = None,
              keep_deps: StrOrListOpt = None,
              visibility: StrOrListOpt = None,
              tags: StrOrListOpt = None,
              warning: str = 'yes',
              defs: StrOrListOpt = None,
              incs: StrOrListOpt = None,
              embed_version: bool = True,
              optimize: StrOrListOpt = None,
              dynamic_link: bool = False,
              linkflags: StrOrListOpt = None,
              extra_cppflags: StrOrListOpt = None,
              extra_cflags: StrOrListOpt = None,
              extra_cxxflags: StrOrListOpt = None,
              extra_asflags: StrOrListOpt = None,
              extra_linkflags: StrOrListOpt = None,
              linker_script: str | None = None,
              linker_scripts: StrOrListOpt = None,
              export_map: str | None = None,
              version_scripts: StrOrListOpt = None,
              export_dynamic: bool = False,
              **kwargs: object):
    """cc_binary target."""
    keep_deps = var_to_list(keep_deps)
    cc_binary_target = CcBinary(
            name=name,
            srcs=srcs,
            deps=var_to_list(deps) + keep_deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            defs=defs,
            incs=incs,
            embed_version=embed_version,
            optimize=optimize,
            dynamic_link=dynamic_link,
            linkflags=linkflags,
            extra_cppflags=extra_cppflags,
            extra_cflags=extra_cflags,
            extra_cxxflags=extra_cxxflags,
            extra_asflags=extra_asflags,
            extra_linkflags=extra_linkflags,
            linker_script=linker_script,
            linker_scripts=linker_scripts,
            export_map=export_map,
            version_scripts=version_scripts,
            export_dynamic=export_dynamic,
            kwargs=kwargs)
    cc_binary_target.attr['keep_deps'] = [cc_binary_target._unify_dep(d) for d in keep_deps]
    build_manager.instance.register_target(cc_binary_target)


build_rules.register_function(cc_binary)


def cc_benchmark(
        name: str,
        deps: StrOrListOpt = None,
        **kwargs: Any):
    """cc_benchmark target."""
    cc_config = config.get_section('cc_config')
    benchmark_libs = cc_config['benchmark_libs']
    benchmark_main_libs = cc_config['benchmark_main_libs']
    deps = var_to_list(deps) + benchmark_libs + benchmark_main_libs
    cc_binary(name=name, deps=deps, **kwargs)


build_rules.register_function(cc_benchmark)


class CcPlugin(CcTarget):
    """
    This class is derived from CcTarget and it generates the cc_plugin
    rules according to user options.
    """

    def __init__(self,
                 name: str,
                 srcs: 'StrOrListOpt',
                 deps: 'StrOrListOpt',
                 visibility: 'StrOrListOpt',
                 tags: 'StrOrListOpt',
                 warning: str,
                 defs: 'StrOrListOpt',
                 incs: 'StrOrListOpt',
                 optimize: 'StrOrListOpt',
                 prefix: str | None,
                 suffix: str | None,
                 linkflags: 'StrOrListOpt',
                 extra_cppflags: 'StrOrListOpt',
                 extra_cflags: 'StrOrListOpt',
                 extra_cxxflags: 'StrOrListOpt',
                 extra_asflags: 'StrOrListOpt',
                 extra_linkflags: 'StrOrListOpt',
                 linker_script: str | None,
                 linker_scripts: 'StrOrListOpt',
                 export_map: str | None,
                 version_scripts: 'StrOrListOpt',
                 allow_undefined: bool,
                 strip: bool,
                 kwargs: dict[str, object]):
        """Init method.

        Init the cc plugin target.

        """
        # Normalize the BUILD-file-friendly StrOrList unions once, right at
        # the rule boundary, so everything downstream sees list[str].
        # `visibility`, `optimize` and `linkflags` keep None-sentinel
        # semantics and are handled via var_to_list_or_none to match
        # CcTarget.__init__.
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        defs = var_to_list(defs)
        incs = var_to_list(incs)
        extra_cppflags = var_to_list(extra_cppflags)
        extra_linkflags = var_to_list(extra_linkflags)
        visibility = var_to_list_or_none(visibility)
        optimize = var_to_list_or_none(optimize)
        linkflags = var_to_list_or_none(linkflags)
        super().__init__(
                  name=name,
                  type='cc_plugin',
                  srcs=srcs,
                  deps=deps,
                  visibility=visibility,
                  tags=tags,
                  warning=warning,
                  defs=defs,
                  incs=incs,
                  export_incs=[],
                  optimize=optimize,
                  linkflags=linkflags,
                  extra_cppflags=extra_cppflags,
                  extra_cflags=extra_cflags,
                  extra_cxxflags=extra_cxxflags,
                  extra_asflags=extra_asflags,
                  extra_linkflags=extra_linkflags,
                  kwargs=kwargs)
        # Soft-deprecation: before this change, `cc_plugin(name='foo.so')` was
        # the only way to override the 'lib%s.so' output basename (because
        # prefix/suffix were silently ignored). Now that prefix/suffix are
        # honored, a name ending in a shared-library extension is ambiguous:
        # under the new rules it would produce e.g. 'libfoo.so.so'. Warn the
        # user so they can switch to the documented `prefix=''` / `suffix=''`
        # spelling instead.
        tc = self.blade.get_build_toolchain()
        if (name.endswith(tc.all_dynamic_lib_suffixes)
                and prefix is None and suffix is None):
            self.warning(
                f"cc_plugin name='{name}' ends in a shared-library extension; "
                "the historical auto-strip behavior has been removed. "
                "Pass prefix='' and suffix='<ext>' explicitly, or rename the "
                "target, to control the output file name."
            )
        self.attr['prefix'] = prefix
        self.attr['suffix'] = suffix
        self.attr['allow_undefined'] = allow_undefined
        self.attr['strip'] = strip
        self.attr['linker_script_fullpath'] = self._resolve_linker_input_file(
            linker_script, linker_scripts, 'linker_script', 'linker_scripts')
        self.attr['export_map_fullpath'] = self._resolve_linker_input_file(
            export_map, version_scripts, 'export_map', 'version_scripts')
        self._add_tags('lang:cc', 'type:plugin')

    def _before_generate(self):  # override
        """Override"""
        self._write_inclusion_check_info()

    def generate(self):
        """Generate build code for cc plugin."""
        objs, inclusion_check_result = self._cc_objects(self.attr['expanded_srcs'])
        target_linkflags = self._generate_link_flags()
        sys_libs, usr_libs, link_all_symbols_libs, incchk_deps = self._static_dependencies()
        if link_all_symbols_libs:
            target_linkflags += self._generate_link_all_symbols_link_flags(link_all_symbols_libs)

        # Honor user-supplied prefix / suffix; fall back to the current
        # toolchain defaults when either is left as None. See
        # :func:`_cc_plugin_default_prefix_suffix` for the cross-platform
        # defaults.
        default_prefix, default_suffix = _cc_plugin_default_prefix_suffix(
            self.blade.get_build_toolchain())
        prefix = default_prefix if self.attr['prefix'] is None else self.attr['prefix']
        suffix = default_suffix if self.attr['suffix'] is None else self.attr['suffix']
        output = self._target_file_path(f'{prefix}{self.name}{suffix}')
        if self.srcs or self.expanded_deps:
            if inclusion_check_result:
                incchk_deps.append(inclusion_check_result)
            if self.attr['strip']:
                link_output = '%s.unstripped' % output
            else:
                link_output = output
            self._cc_link(link_output, 'solink', objs=objs, deps=usr_libs, sys_libs=sys_libs,
                          linker_scripts=self.attr.get('linker_script_fullpath'),
                          version_scripts=self.attr.get('export_map_fullpath'),
                          target_linkflags=target_linkflags,
                          implicit_deps=link_all_symbols_libs, order_only_deps=incchk_deps)
            if self.attr['strip']:
                if self.blade.get_build_toolchain().cc_is('gcc'):
                    self.generate_build('strip', output, inputs=link_output)
                else:
                    console.notice('strip is not supported on this toolchain, skipping')
            self._add_default_target_file(self.blade.get_build_toolchain().DYNAMIC_LIB_LABEL, output)


def cc_plugin(
        name: str,
        srcs: 'StrOrListOpt' = None,
        deps: 'StrOrListOpt' = None,
        keep_deps: 'StrOrListOpt' = None,
        visibility: 'StrOrListOpt' = None,
        tags: 'StrOrListOpt' = None,
        warning: str = 'yes',
        defs: 'StrOrListOpt' = None,
        incs: 'StrOrListOpt' = None,
        optimize: 'StrOrListOpt' = None,
        prefix: str | None = None,
        suffix: str | None = None,
        linkflags: 'StrOrListOpt' = None,
        extra_cppflags: 'StrOrListOpt' = None,
        extra_cflags: 'StrOrListOpt' = None,
        extra_cxxflags: 'StrOrListOpt' = None,
        extra_asflags: 'StrOrListOpt' = None,
        extra_linkflags: 'StrOrListOpt' = None,
        linker_script: str | None = None,
        linker_scripts: 'StrOrListOpt' = None,
        export_map: str | None = None,
        version_scripts: 'StrOrListOpt' = None,
        allow_undefined: bool = True,
        strip: bool = False,
        **kwargs: object):
    """cc_plugin target."""
    keep_deps = var_to_list(keep_deps)
    target = CcPlugin(
            name=name,
            srcs=srcs,
            deps=var_to_list(deps) + keep_deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            defs=defs,
            incs=incs,
            optimize=optimize,
            prefix=prefix,
            suffix=suffix,
            linkflags=linkflags,
            extra_cppflags=extra_cppflags,
            extra_cflags=extra_cflags,
            extra_cxxflags=extra_cxxflags,
            extra_asflags=extra_asflags,
            extra_linkflags=extra_linkflags,
            linker_script=linker_script,
            linker_scripts=linker_scripts,
            export_map=export_map,
            version_scripts=version_scripts,
            allow_undefined=allow_undefined,
            strip=strip,
            kwargs=kwargs)
    target.attr['keep_deps'] = [target._unify_dep(d) for d in keep_deps]
    build_manager.instance.register_target(target)


build_rules.register_function(cc_plugin)


class CcTest(CcBinary):
    """
    This class is derived from CcTarget and it generates the cc_test
    rules according to user options.
    """

    def __init__(
            self,
            name: str | None,
            srcs: StrOrListOpt,
            deps: StrOrListOpt,
            visibility: StrOrListOpt,
            tags: StrOrListOpt,
            warning: str,
            defs: StrOrListOpt,
            incs: StrOrListOpt,
            embed_version: bool,
            optimize: StrOrListOpt,
            dynamic_link: bool | None,
            testdata: StrOrListOpt,
            linkflags: StrOrListOpt,
            extra_cppflags: StrOrListOpt,
            extra_cflags: StrOrListOpt,
            extra_cxxflags: StrOrListOpt,
            extra_asflags: StrOrListOpt,
            extra_linkflags: StrOrListOpt,
            export_dynamic: bool,
            always_run: bool,
            exclusive: bool,
            heap_check: str | None,
            heap_check_debug: bool,
            kwargs: dict[str, object]):
        """Init method."""
        # pylint: disable=too-many-locals
        cc_test_config = config.get_section('cc_test_config')
        if dynamic_link is None:
            dynamic_link = bool(cc_test_config['dynamic_link'])

        super().__init__(
                name=name,
                srcs=srcs,
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                embed_version=embed_version,
                optimize=optimize,
                linkflags=linkflags,
                dynamic_link=dynamic_link,
                extra_cppflags=extra_cppflags,
                extra_cflags=extra_cflags,
                extra_cxxflags=extra_cxxflags,
                extra_asflags=extra_asflags,
                extra_linkflags=extra_linkflags,
                linker_script=None,
                linker_scripts=[],
                export_map=None,
                version_scripts=[],
                export_dynamic=export_dynamic,
                kwargs=kwargs)
        self.type = 'cc_test'
        self.attr['testdata'] = var_to_list(testdata)
        self.attr['always_run'] = always_run
        self.attr['exclusive'] = exclusive
        self._add_tags('lang:cc', 'type:test')

        gtest_lib = var_to_list(cc_test_config['gtest_libs'])
        gtest_main_lib = var_to_list(cc_test_config['gtest_main_libs'])

        # Hardcode deps rule to thirdparty gtest main lib.
        self._add_implicit_library(gtest_lib)
        self._add_implicit_library(gtest_main_lib)

        if heap_check is None:
            heap_check = cc_test_config.get('heap_check', '')
        elif heap_check not in HEAP_CHECK_VALUES:
            self.error('heap_check can only be in %s' % HEAP_CHECK_VALUES)
            heap_check = ''

        perftools_lib = var_to_list(cc_test_config['gperftools_libs'])
        perftools_debug_lib = var_to_list(cc_test_config['gperftools_debug_libs'])
        if heap_check:
            self.attr['heap_check'] = heap_check

            if heap_check_debug:
                perftools_lib_list = perftools_debug_lib
            else:
                perftools_lib_list = perftools_lib

            self._add_implicit_library(perftools_lib_list)


def cc_test(name: str,
            srcs: StrOrListOpt = None,
            deps: StrOrListOpt = None,
            keep_deps: StrOrListOpt = None,
            visibility: StrOrListOpt = None,
            tags: StrOrListOpt = None,
            warning: str = 'yes',
            defs: StrOrListOpt = None,
            incs: StrOrListOpt = None,
            embed_version: bool = False,
            optimize: StrOrListOpt = None,
            dynamic_link: bool | None = None,
            testdata: StrOrListOpt = None,
            linkflags: StrOrListOpt = None,
            extra_cppflags: StrOrListOpt = None,
            extra_cflags: StrOrListOpt = None,
            extra_cxxflags: StrOrListOpt = None,
            extra_asflags: StrOrListOpt = None,
            extra_linkflags: StrOrListOpt = None,
            export_dynamic: bool = False,
            always_run: bool = False,
            exclusive: bool = False,
            heap_check: str | None = None,
            heap_check_debug: bool = False,
            **kwargs: object):
    """cc_test target."""
    # pylint: disable=too-many-locals
    keep_deps = var_to_list(keep_deps)
    cc_test_target = CcTest(
            name=name,
            srcs=srcs,
            deps=var_to_list(deps) + keep_deps,
            visibility=visibility,
            tags=tags,
            warning=warning,
            defs=defs,
            incs=incs,
            embed_version=embed_version,
            optimize=optimize,
            dynamic_link=dynamic_link,
            testdata=testdata,
            linkflags=linkflags,
            extra_cppflags=extra_cppflags,
            extra_cflags=extra_cflags,
            extra_cxxflags=extra_cxxflags,
            extra_asflags=extra_asflags,
            extra_linkflags=extra_linkflags,
            export_dynamic=export_dynamic,
            always_run=always_run,
            exclusive=exclusive,
            heap_check=heap_check,
            heap_check_debug=heap_check_debug,
            kwargs=kwargs)
    cc_test_target.attr['keep_deps'] = [cc_test_target._unify_dep(d) for d in keep_deps]
    build_manager.instance.register_target(cc_test_target)


build_rules.register_function(cc_test)


rule_registry.register_rule_provider(
    cc_rule_support.generate_cc_rules, order=rule_registry.ORDER_CC, name='cc')
