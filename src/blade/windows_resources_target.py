# Copyright (c) 2025 Tencent Inc.
# All rights reserved.
#
# Author: Feng Chen <phongchen@tencent.com>


"""
Windows Resource Compiler build rule.

Compiles ``.rc`` resource script files into ``.res`` object files using
the Windows SDK Resource Compiler (``rc.exe``).  These ``.res`` files can
be linked into ``cc_binary`` targets (MSVC ``link.exe`` accepts ``.res``
files as positional inputs).

On non-Windows platforms this rule is a no-op — ``generate()`` returns
immediately and ``_get_target_files()`` yields nothing.

Design follows Bazel's ``win_res.bzl``: the target stores compiled ``.res``
paths in ``data['res_files']`` (analogous to ``CcInfo(linking_context=...)``),
which downstream ``cc_binary`` targets collect in their dependency resolution.
"""


import os
from blade import build_manager
from blade import build_rules
from blade import console
from blade.blade_types import StrOrListOpt
from blade.target import Target
from blade.util import var_to_list, var_to_list_or_none, regular_variable_name


class WindowsResourcesTarget(Target):
    """Compile Windows ``.rc`` resource files into ``.res`` object files."""

    def __init__(
            self,
            name: str,
            rc_files: StrOrListOpt,
            hdrs: StrOrListOpt = None,
            resources: StrOrListOpt = None,
            deps: StrOrListOpt = None,
            visibility: StrOrListOpt = None,
            kwargs: dict | None = None) -> None:
        kwargs = kwargs or {}
        rc_files = var_to_list(rc_files)
        if not rc_files:
            self.error('"rc_files" can not be empty')

        hdrs = var_to_list(hdrs) if hdrs else []
        resources = var_to_list(resources) if resources else []
        deps = var_to_list(deps) if deps else []
        visibility = var_to_list_or_none(visibility)

        # Validate file extensions
        for rc in rc_files:
            if not rc.endswith('.rc'):
                self.error('rc_files must be .rc files: %s' % rc)

        srcs = rc_files + hdrs + resources
        super().__init__(
            name=name,
            type='windows_resources',
            srcs=srcs,
            src_exts=[],  # Allow any extension
            deps=deps,
            visibility=visibility,
            tags=[],
            kwargs=kwargs)
        self._add_tags('type:windows_resources')

        self.attr['rc_files'] = rc_files
        self.attr['hdrs'] = hdrs
        self.attr['resources'] = resources

    def _allow_duplicate_source(self):
        return True

    def generate(self):
        """Generate Ninja build edges for compiling .rc files."""
        toolchain = self.blade.get_build_toolchain()
        rc_exe = toolchain.tool('rc')
        if not rc_exe:
            # No-op when the toolchain doesn't support .rc compilation.
            return

        # Gather SDK include paths (um/, shared/ subdirs) for rc.exe
        system_includes = toolchain.get_system_include_paths()
        sdk_inc_flags = []
        for p in system_includes:
            # rc.exe uses /i for #include paths; quote paths with spaces
            quoted = '"%s"' % p if ' ' in p else p
            sdk_inc_flags.append('/i%s' % quoted)

        # Add the source directory so rc.exe can resolve #include "..." and
        # ICON / BITMAP references relative to the .rc file's location.
        src_dir = os.path.join(self.blade.get_root_dir(), self.path)
        sdk_inc_flags.append('/i"%s"' % src_dir)

        inc_flags = ' '.join(sdk_inc_flags)

        # Per-target ninja rule for rc.exe
        rule_name = 'rc_%s' % regular_variable_name(self._source_file_path(self.name))
        rc_command = '"%s" /nologo /fo${out} %s ${in}' % (rc_exe, inc_flags)
        self._write_rule('rule %s\n  command = %s\n  description = RC ${in}\n' % (
            rule_name, rc_command))

        # Build edges: one per .rc file
        rc_inputs = [self._source_file_path(rc) for rc in self.attr['rc_files']]
        resource_inputs = [self._source_file_path(r) for r in self.attr['resources']]
        hdr_inputs = [self._source_file_path(h) for h in self.attr['hdrs']]

        # Resources and headers referenced by the .rc are implicit deps:
        # if they change Ninja rebuilds the .res, but they don't appear in
        # ${in} on the rc.exe command line.
        implicit_deps = resource_inputs + hdr_inputs

        res_paths = []
        for i, rc_file in enumerate(self.attr['rc_files']):
            res_path = self._target_file_path(rc_file + '.res')
            res_paths.append(res_path)
            self.generate_build(
                rule_name,
                res_path,
                inputs=[self._source_file_path(rc_file)],
                implicit_deps=implicit_deps)
            self._add_target_file('res_%d' % i, res_path)

        # Expose .res paths for downstream cc_binary dep resolution
        # (analogous to Bazel's CcInfo linking context propagation).
        self.data['res_files'] = res_paths


def windows_resources(
        name: str,
        rc_files: StrOrListOpt = None,
        hdrs: StrOrListOpt = None,
        resources: StrOrListOpt = None,
        deps: StrOrListOpt = None,
        visibility: StrOrListOpt = None,
        **kwargs: object) -> None:
    """Compile Windows resource (``.rc``) files into ``.res`` object files.

    The resulting ``.res`` files are automatically linked into any
    ``cc_binary`` that depends on this target via ``deps``.

    On non-Windows platforms this rule is a no-op and resolves to nothing.
    """
    target = WindowsResourcesTarget(
        name=name,
        rc_files=rc_files,
        hdrs=hdrs,
        resources=resources,
        deps=deps,
        visibility=visibility,
        kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(windows_resources)
