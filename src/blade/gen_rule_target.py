# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""General Build Rule
Allow users defining their custom build rules.
"""


import os
import re

from blade import build_manager
from blade import build_rules
from blade import cc_targets
from blade import console
from blade import gen_command
from blade.blade_types import StrOrListOpt
from blade.target import Target
from blade.util import regular_variable_name
from blade.util import var_to_list, var_to_list_or_none


# $(location //x:y) -> a dep's single output; $(locations //x:y) -> all of its
# outputs (space-joined). Combined into one regex so left-to-right order is
# preserved for the positional %s expansion. Group 1 = the optional plural 's',
# group 2 = the target key, group 3 = the optional output label.
_LOCATION_RE = re.compile(r'\$\(location(s)?\s+(\S*:\S+)(\s+\w*)?\)')


# The rule template for gen_rule. The command is fully wrapped by
# `_wrap_command` (interpreter + output-existence check), so nothing
# shell-specific is hard-coded here -- see issue #1204.
_RULE_FORMAT = '''\
rule %s
  command = %s
  description = %s
'''


class GenRuleTarget(Target):
    """General Rule Target"""

    def __init__(self,
                 name: str | None,
                 srcs: StrOrListOpt,
                 src_exts: StrOrListOpt,
                 deps: StrOrListOpt,
                 visibility: StrOrListOpt,
                 tags: StrOrListOpt,
                 outs: StrOrListOpt,
                 cmd: str,
                 cmd_bash: str,
                 cmd_bat: str,
                 cmd_name: str,
                 generated_hdrs: StrOrListOpt,
                 generated_incs: StrOrListOpt,
                 export_incs: StrOrListOpt,
                 system_export_incs: StrOrListOpt,
                 cleans: StrOrListOpt,
                 heavy: bool,
                 exclude_dep_labels: StrOrListOpt,
                 kwargs: dict[str, object]):
        """Init method.
        Init the gen rule target.
        """
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        src_exts = var_to_list(src_exts) if src_exts is not None else None
        tags = var_to_list(tags)
        visibility = var_to_list_or_none(visibility)
        super().__init__(
                name=name,
                type='gen_rule',
                srcs=srcs,
                src_exts=src_exts if src_exts is not None else [],
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)
        self._add_tags('type:gen_rule')
        if not outs:
            self.error('"outs" can not be empty')
        selected_cmd, self._gen_kind, self._bash = self._select_command(
            cmd, cmd_bash, cmd_bat)
        if not selected_cmd:
            self.error('one of "cmd", "cmd_bash", "cmd_bat" must be set '
                       '(and usable on this platform)')
            selected_cmd = ''
        outs = var_to_list(outs)
        # self._check_path_list(outs, "outs", must_exist=False)
        outs = [os.path.normpath(o) for o in outs]
        for o in outs:
            if '..' in o.split(os.sep):
                self.error('"outs" must not contain "..": %s' % o)

        self.attr['outs'] = var_to_list(outs)
        self.attr['outputs'] = [self._target_file_path(o) for o in self.attr['outs']]
        self.attr['locations'] = []
        self.attr['cmd'] = _LOCATION_RE.sub(self._process_location_reference, selected_cmd)
        self.attr['cmd_name'] = cmd_name
        self.attr['heavy'] = heavy
        self.attr['exclude_dep_labels'] = exclude_dep_labels
        self.cleans = var_to_list(cleans)
        for clean in self.cleans:
            self._remove_on_clean(self._target_file_path(clean))

        if generated_incs is not None:
            for inc in generated_incs:
                generated_incs = var_to_list(generated_incs)
                cc_targets.declare_hdr_dir(self, inc)
            generated_incs = [self._target_file_path(inc) for inc in generated_incs]
            self.attr['generated_incs'] = generated_incs
        else:
            if generated_hdrs is None:
                # Auto judge
                generated_hdrs = [o for o in outs if cc_targets.is_header_file(o)]
            else:
                generated_hdrs = var_to_list(generated_hdrs)
            if generated_hdrs:
                cc_targets.declare_hdrs(self, generated_hdrs)
                generated_hdrs = [self._target_file_path(h) for h in generated_hdrs]
                self.attr['generated_hdrs'] = generated_hdrs

        if export_incs:
            self.attr['export_incs'] = self._expand_incs(var_to_list(export_incs))
        if system_export_incs:
            self.attr['system_export_incs'] = self._expand_incs(
                var_to_list(system_export_incs))

    @staticmethod
    def _select_command(cmd, cmd_bash, cmd_bat):
        """Pick the command + how to run it for the host platform (see
        :func:`gen_command.select_command`)."""
        return gen_command.select_command(cmd, cmd_bash, cmd_bat)

    def _output_check(self, shell):
        """Per-output existence check in the given shell (see gen_command)."""
        return gen_command.output_check(shell, self.attr['outputs'], self.blade.get_root_dir())

    def _wrap_command(self, cmd):
        """Wrap the user command with the right interpreter + output check."""
        return gen_command.wrap_command(
            cmd, self._gen_kind, self._bash, self.attr['outputs'], self.blade.get_root_dir())

    def _expand_incs(self, incs):
        """Expand incs"""
        return [self._target_file_path(inc) for inc in incs]

    def _process_location_reference(self, m):
        """Process a $(location ...) / $(locations ...) reference.

        Registers the referenced target as a dep and records (key, label,
        plural) for expansion. Returns a '%s' placeholder, filled positionally
        in `_expand_command` (one combined regex keeps left-to-right order).
        """
        plural = bool(m.group(1))
        key = self._unify_dep(m.group(2))
        label = (m.group(3) or '').strip()
        if key and key not in self.deps:
            self.deps.append(key)
        self.attr['locations'].append((key, label, plural))
        return '%s'  # Will be expanded in `_expand_command`

    def _index_ref(self, sel, names, paths, what):
        """Resolve $OUTS[sel] / $SRCS[sel] to one path (see gen_command)."""
        return gen_command.index_ref(sel, names, paths, what, self.error)

    def _allow_duplicate_source(self):
        return True

    def _expand_command(self):
        """Expand vars and location references in command.

        For the bash kind, all paths are emitted with forward slashes (Windows
        backslashes are escapes in bash) -- and `$SRCS`/`$OUTS`/`$FIRST_*` are
        substituted as concrete paths rather than ninja `${in}`/`${out}`, which
        ninja would render with backslashes on Windows. cmd/raw keep the ninja
        vars + OS-native separators (correct for cmd.exe / POSIX sh).
        """
        posix = self._gen_kind == 'bash'
        cmd = gen_command.expand_vars(
            self.attr['cmd'], bash=posix,
            src_names=self.srcs, src_paths=self._expand_srcs(),
            out_names=self.attr['outs'], out_paths=self.attr['outputs'],
            path=self.path, build_dir=self.build_dir, error=self.error)

        def _p(path):
            return path.replace('\\', '/') if posix else path

        locations = self.attr['locations']
        if locations:
            targets = self.blade.get_build_targets()
            locations_paths = []
            for key, label, plural in locations:
                if plural:
                    files = targets[key]._get_target_files()
                    if not files:
                        self.error('Invalid locations reference %s' % ':'.join(key))
                        continue
                    locations_paths.append(' '.join(_p(f) for f in files))
                    continue
                path = targets[key]._get_target_file(label)
                if not path:
                    self.error('Invalid location reference {} {}'.format(':'.join(key), label))
                    continue
                locations_paths.append(_p(path))
            cmd = cmd % tuple(locations_paths)
        return cmd

    def implicit_dependencies(self):
        targets = self.blade.get_build_targets()
        implicit_deps = []
        for dep in self.deps:
            # FIXME: incchk.result file should be ordered_only_deps
            implicit_deps += targets[dep]._get_target_files(exclude_labels=self.attr['exclude_dep_labels'])
        return implicit_deps

    def _expand_srcs(self):
        result = []
        for s in self.srcs:
            src = self._source_file_path(s)
            if os.path.exists(src):
                result.append(src)
            else:
                result.append(self._target_file_path(s))
        return result

    def generate(self):
        """Generate code for backend build system."""
        # NOTE: Here is something different with normal targets.
        # We have to generate each `rule` for a `gen_rule` target but not sharing a predefined rule.
        # Because the `command` variable is not lazy evaluated althrough it can be overridden in a
        # `build` statement, so any other build scoped variables are expanded to empty.
        rule = '%s__rule__' % regular_variable_name(self._source_file_path(self.name))
        cmd = self._wrap_command(self._expand_command())
        description = f"{self.attr['cmd_name']} {self.fullname}"
        self._write_rule(_RULE_FORMAT % (rule, cmd, description))

        outputs = self.attr['outputs']
        inputs = self._expand_srcs()
        vars = {}
        if '${_in_1}' in cmd:
            vars['_in_1'] = inputs[0]
        if '${_out_1}' in cmd:
            vars['_out_1'] = outputs[0]
        if self.attr['heavy']:
            vars['pool'] = 'heavy_pool'
        self.generate_build(rule, outputs, inputs=inputs, implicit_deps=self.implicit_dependencies(),
                            variables=vars)

        for i, out in enumerate(outputs):
            self._add_target_file(str(i), out)


def gen_rule(
        name: str,
        srcs: StrOrListOpt = None,
        src_exts: StrOrListOpt = None,
        deps: StrOrListOpt = None,
        visibility: StrOrListOpt = None,
        tags: StrOrListOpt = None,
        outs: StrOrListOpt = None,
        cmd: str = '',
        cmd_bash: str = '',
        cmd_bat: str = '',
        cmd_name: str = 'COMMAND',
        generated_hdrs: StrOrListOpt = None,
        generated_incs: StrOrListOpt = None,
        export_incs: StrOrListOpt = None,
        system_export_incs: StrOrListOpt = None,
        cleans: StrOrListOpt = None,
        heavy: bool = False,
        exclude_dep_labels: StrOrListOpt = None,
        **kwargs: object):
    """General Build Rule
    Args:
        cmd: str, the command, run by the host's default shell (``/bin/sh`` on
            POSIX, ``cmd.exe`` on Windows). The generic, back-compatible form.
        cmd_bash: str, a command run via ``bash`` (``set -e -o pipefail``).
            Preferred on POSIX, and on Windows when bash is available.
        cmd_bat: str, a Windows batch command run via
            ``cmd.exe /S /E:ON /V:ON /D /c``. Preferred on Windows.
            At least one of ``cmd`` / ``cmd_bash`` / ``cmd_bat`` is required;
            the platform-appropriate one is selected automatically (#1204).
        src_exts: List[str],
            Valid extension names for file in "srcs", can be None, which means any is valid.
            NOTE the empty string is also a valid extension, which means NO extension.
            For example, if it is ['h', ''], 'vector' and 'vector.h' are both valid.
        generated_hdrs: Optional[bool],
            Specify whether this target will generate c/c++ header files.
            Defaultly, gen_rule will calculate a generated header files list automatically
            according to the names in the |outs|`
            But if they are not specified in the outs, and we sure know this target will generate
            some headers, we should set this argument to True.
        export_incs: List(str), the include dirs to be exported to dependants, NOTE these dirs are
            under the target dir, it's different with cc_library.export_incs.
        system_export_incs: List(str), like ``export_incs`` but consumers emit ``-isystem`` instead
            of ``-I`` for these paths. Use for third-party / generated headers whose own diagnostics
            should not contribute to the consumer's ``-Werror`` budget. Same path semantics
            (under the target dir).
        cleans: List(str), The paths to be removed in the clean command, relative to the output
            directory.
        exclude_dep_labels: List(str), the dependency labels to be excluded.
            Some labels in deps are not necessary for the gen_rule. For example,
            the dwp of binary is not necessary if gen_rule use $(location :binary) as argument.
        heavy: bool, Whether this target is a heavy target, which means to build it will cost many
            cpu/memory.
    """
    if exclude_dep_labels is None:
        exclude_dep_labels = ["dwp"]
    gen_rule_target = GenRuleTarget(
            name=name,
            srcs=srcs,
            src_exts=src_exts,
            deps=deps,
            visibility=visibility,
            tags=tags,
            outs=outs,
            cmd=cmd,
            cmd_bash=cmd_bash,
            cmd_bat=cmd_bat,
            cmd_name=cmd_name,
            generated_hdrs=generated_hdrs,
            generated_incs=generated_incs,
            export_incs=export_incs,
            system_export_incs=system_export_incs,
            cleans=cleans,
            heavy=heavy,
            exclude_dep_labels=exclude_dep_labels,
            kwargs=kwargs)
    build_manager.instance.register_target(gen_rule_target)


build_rules.register_function(gen_rule)
