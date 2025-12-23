# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""General Build Rule
Allow users defining their custom build rules.
"""

from __future__ import absolute_import
from __future__ import print_function

import os

from blade import build_manager
from blade import build_rules
from blade import cc_targets
from blade import console
from blade.target import Target, LOCATION_RE
from blade.util import regular_variable_name
from blade.util import var_to_list


# The rule template for gen_rule
_RULE_FORMAT = '''\
rule %s
  command = %s && cd %s && ls ${out} > /dev/null
  description = %s
'''


class GenRuleTarget(Target):
    """General Rule Target"""

    def __init__(self,
                 name,
                 srcs,
                 src_exts,
                 deps,
                 visibility,
                 tags,
                 outs,
                 cmd,
                 cmd_name,
                 generated_hdrs,
                 generated_incs,
                 export_incs,
                 cleans,
                 heavy,
                 exclude_dep_labels,
                 kwargs):
        """Init method.
        Init the gen rule target.
        """
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        super(GenRuleTarget, self).__init__(
                name=name,
                type='gen_rule',
                srcs=srcs,
                src_exts=src_exts,
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)
        self._add_tags('type:gen_rule')
        if not outs:
            self.error('"outs" can not be empty')
        if not cmd:
            self.error('"cmd" can not be empty')
        outs = var_to_list(outs)
        # self._check_path_list(outs, "outs", must_exist=False)
        outs = [os.path.normpath(o) for o in outs]

        self.attr['outs'] = outs
        self.attr['outputs'] = [self._target_file_path(o) for o in self.attr['outs']]
        self.attr['locations'] = []
        self.attr['cmd'] = LOCATION_RE.sub(self._process_location_reference, cmd)
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

    def _expand_incs(self, incs):
        """Expand incs"""
        return [self._target_file_path(inc) for inc in incs]

    def _process_location_reference(self, m):
        """Process target location reference in the command."""
        key, type = self._add_location_reference_target(m)
        self.attr['locations'].append((key, type))
        return '%s'  # Will be expanded in `_expand_command`

    def _allow_duplicate_source(self):
        return True

    def _expand_command(self):
        """Expand vars and location references in command"""
        cmd = self.attr['cmd']
        cmd = cmd.replace('$SRCS', '${in}')
        cmd = cmd.replace('$OUTS', '${out}')
        cmd = cmd.replace('$FIRST_SRC', '${_in_1}')
        cmd = cmd.replace('$FIRST_OUT', '${_out_1}')
        cmd = cmd.replace('$SRC_DIR', self.path)
        cmd = cmd.replace('$OUT_DIR', os.path.join(self.build_dir, self.path))
        cmd = cmd.replace('$BUILD_DIR', self.build_dir)
        locations = self.attr['locations']
        if locations:
            targets = self.blade.get_build_targets()
            locations_paths = []
            for key, label in locations:
                path = targets[key]._get_target_file(label)
                if not path:
                    self.error('Invalid location reference %s %s' % (':'.join(key), label))
                    continue
                locations_paths.append(path)
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
        cmd = self._expand_command()
        description = console.colored('%s %s' % (self.attr['cmd_name'], self.fullname), 'dimpurple')
        self._write_rule(_RULE_FORMAT % (rule, cmd, self.blade.get_root_dir(), description))

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
        name,
        srcs=[],
        src_exts=[],
        deps=[],
        visibility=None,
        tags=[],
        outs=[],
        cmd='',
        cmd_name='COMMAND',
        generated_hdrs=None,
        generated_incs=None,
        export_incs=[],
        cleans=[],
        heavy=False,
        exclude_dep_labels=["dwp"],
        **kwargs):
    """General Build Rule
    Args:
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
        cleans: List(str), The paths to be removed in the clean command, relative to the output
            directory.
        exclude_dep_labels: List(str), the dependency labels to be excluded.
            Some labels in deps are not necessary for the gen_rule. For example,
            the dwp of binary is not necessary if gen_rule use $(location :binary) as argument.
        heavy: bool, Whether this target is a heavy target, which means to build it will cost many
            cpu/memory.
    """
    gen_rule_target = GenRuleTarget(
            name=name,
            srcs=srcs,
            src_exts=src_exts,
            deps=deps,
            visibility=visibility,
            tags=tags,
            outs=outs,
            cmd=cmd,
            cmd_name=cmd_name,
            generated_hdrs=generated_hdrs,
            generated_incs=generated_incs,
            export_incs=export_incs,
            cleans=cleans,
            heavy=heavy,
            exclude_dep_labels=exclude_dep_labels,
            kwargs=kwargs)
    build_manager.instance.register_target(gen_rule_target)


build_rules.register_function(gen_rule)
