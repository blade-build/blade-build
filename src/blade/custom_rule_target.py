# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""User-defined custom rules (issue #829).

`define_rule(...)` (a `.bld`-only builtin) declares a new rule type with a typed
attribute schema and a Python ``action``. The returned function is used in BUILD
files (after ``load``) like a native rule; it instantiates a generic
:class:`CustomRuleTarget` whose ``generate()`` runs the action in the analysis
phase -- the action only *registers* ninja edges (it never executes commands or
touches files), reusing the same machinery as ``gen_rule`` (see ``gen_command``).
"""

import functools
import inspect
import os
from typing import cast

from blade import build_manager
from blade import build_rules
from blade import cc_targets
from blade import config
from blade import console
from blade import gen_command
from blade import rule_registry
from blade.blade_types import StrOrListOpt
from blade.target import Target
from blade.util import md5sum, md5sum_file, var_to_list, var_to_list_or_none
from blade.util import regular_variable_name


_RULE_FORMAT = '''\
rule %s
  command = %s
  description = %s
'''

# Attribute kinds whose value is a list (coerced via var_to_list).
_LIST_KINDS = ('string_list', 'src_list', 'dep_list', 'out_list')


class Attr:
    """A custom-rule attribute declaration. Kept serializable for fingerprinting
    (no callables / objects -- only the kind string, a plain default, bools)."""

    __slots__ = ('kind', 'default', 'mandatory', 'exts')

    def __init__(self, kind, default=None, mandatory=False, exts=None):
        self.kind = kind
        self.default = default
        self.mandatory = mandatory
        self.exts = exts


class _AttrNamespace:
    """The ``attr`` builtin available in ``.bld`` files: ``attr.string(...)`` etc."""

    def string(self, default='', mandatory=False):
        return Attr('string', default, mandatory)

    def bool(self, default=False, mandatory=False):
        return Attr('bool', default, mandatory)

    def int(self, default=0, mandatory=False):
        return Attr('int', default, mandatory)

    def string_list(self, default=(), mandatory=False):
        return Attr('string_list', list(default), mandatory)

    def src_list(self, default=(), exts=None, mandatory=False):
        return Attr('src_list', list(default), mandatory, exts)

    def dep_list(self, default=(), mandatory=False):
        return Attr('dep_list', list(default), mandatory)

    def out_list(self, default=(), mandatory=False):
        return Attr('out_list', list(default), mandatory)


# The singleton injected into `.bld` globals (see build_rules.get_all_for_extension).
attr = _AttrNamespace()


class _Actions:
    """`ctx.actions`: the edge-emitting side of the action context."""

    def __init__(self, target):
        self._t = target

    def run_shell(self, command=None, cmd_bash=None, cmd_bat=None, inputs=None,
                  outputs=None, implicit_deps=None, variables=None, description=None):
        """Emit a per-target rule + build edge running a shell command.

        ``command`` is the generic form (host shell); ``cmd_bash`` / ``cmd_bat``
        are optional platform variants (selected like gen_rule). The command may
        use ``$SRCS/$OUTS/$OUTS[i]/$FIRST_*/$SRC_DIR/...`` (see gen_command).
        ``outputs`` defaults to all outputs declared so far; ``inputs`` to the
        rule's expanded srcs.
        """
        self._t._pending_edges.append(functools.partial(
            self._t._emit_shell_edge, command, cmd_bash, cmd_bat, inputs,
            outputs, implicit_deps, variables, description))

    def shared_rule(self, ninja_rule):
        """Register a shared ninja rule once (idempotent by name) via the
        registry's custom slot, so many edges/targets can reference it."""
        rule_registry.register_rule_provider(
            lambda rc: rc.emit_rule(ninja_rule),
            order=rule_registry.ORDER_CUSTOM,
            name='custom:' + ninja_rule.name)

    def run(self, rule, inputs=None, outputs=None, implicit_deps=None, variables=None):
        """Emit a build edge referencing an already-registered (shared) rule."""
        self._t._pending_edges.append(functools.partial(
            self._t._emit_edge, rule, inputs, outputs, implicit_deps, variables))


class ActionContext:
    """`ctx` passed to a custom rule's action. Read state + emit helpers; runs in
    the analysis phase, so it only registers edges (no file IO / command exec)."""

    def __init__(self, target):
        self._t = target
        self.name = target.name
        self.path = target.path
        self.fullname = target.fullname
        self.build_dir = target.build_dir
        self.target_dir = target.target_dir
        self.attrs = target.attr['custom_attrs']
        self.toolchain = target.blade.get_build_toolchain()
        self.actions = _Actions(target)

    def config(self, section):
        return config.get_section(section)

    def declare_output(self, name):
        """Declare an output file (target-dir relative name); returns full path."""
        return self._t._declare_output(name)

    def declare_header(self, name):
        """Declare a generated header; flows to cc_* deps when provides_cc=True."""
        return self._t._declare_header(name)

    def declare_inc_dir(self, inc):
        """Declare a generated include dir (target-dir relative)."""
        return self._t._declare_inc_dir(inc)

    def deps_outputs(self):
        """All output files of this target's deps."""
        return self._t._deps_outputs()

    def deps_generated_headers(self):
        """(files, dirs) of generated headers/include-dirs from transitive deps."""
        return self._t._deps_generated_headers()


class CustomRuleTarget(Target):
    """Backing target for a user-defined rule (one per BUILD invocation)."""

    def __init__(self, rule_type, schema, action, provides_cc, description,
                 target_name, deps, visibility, tags, attr_values):
        srcs, dep_labels, custom, missing, bad = [], var_to_list(deps), {}, [], []
        for an, spec in schema.items():
            present = an in attr_values
            val = attr_values.pop(an) if present else _default_of(spec)
            if not present and spec.mandatory:
                missing.append(an)
            val = _coerce(spec, val, bad, an)
            if spec.kind == 'src_list':
                srcs += var_to_list(cast(StrOrListOpt, val))
            elif spec.kind == 'dep_list':
                dep_labels += var_to_list(cast(StrOrListOpt, val))
            else:
                custom[an] = val
        unknown = sorted(attr_values)

        super().__init__(name=target_name, type='custom:' + rule_type, srcs=srcs,
                         src_exts=[], deps=dep_labels,
                         visibility=visibility, tags=var_to_list(tags), kwargs={})
        self._add_tags('type:custom_rule')

        for an in missing:
            self.error('missing mandatory attribute "%s"' % an)
        for an, want in bad:
            self.error('attribute "%s" should be %s' % (an, want))
        for an in unknown:
            self.error('unknown attribute "%s" for rule "%s"' % (an, rule_type))

        self.attr['rule_type'] = rule_type
        self.attr['custom_attrs'] = custom
        self.attr['description'] = description
        # Off self.attr (not serializable) -> never in fingerprint entropy.
        self._schema = schema
        self._action = action
        self._provides_cc = provides_cc
        self._outputs = []     # declared by the action (label -> registered too)
        self._edge_seq = 0
        self._pending_edges = []

        # Run the action in the analysis phase (at construction), as Bazel does:
        # outputs are declared NOW (so consumers see generated_hdrs/incs before
        # their own generate()), while build edges are merely recorded here and
        # flushed in generate() once deps are fully resolved.
        self._action(ActionContext(self))
        if not self._outputs:
            self.error('custom rule "%s" action declared no outputs' % rule_type)

    def _allow_duplicate_source(self):
        return True

    # --- output declaration (called from ActionContext) ---

    def _declare_output(self, name):
        path = self._target_file_path(name)
        self._outputs.append(path)
        self._add_target_file(str(len(self._outputs) - 1), path)
        return path

    def _declare_header(self, name):
        path = self._declare_output(name)
        if self._provides_cc:
            cc_targets.declare_hdrs(self, [name])
            self.attr.setdefault('generated_hdrs', []).append(self._target_file_path(name))
        return path

    def _declare_inc_dir(self, inc):
        if self._provides_cc:
            cc_targets.declare_hdr_dir(self, inc)
            self.attr.setdefault('generated_incs', []).append(self._target_file_path(inc))
            self.attr.setdefault('export_incs', []).append(self._target_file_path(inc))
        return self._target_file_path(inc)

    # --- dep introspection ---

    def _expand_srcs(self):
        result = []
        for s in self.srcs:
            src = self._source_file_path(s)
            result.append(src if os.path.exists(src) else self._target_file_path(s))
        return result

    def _implicit_dependencies(self):
        targets = self.blade.get_build_targets()
        files = []
        for dep in self.deps:
            files += targets[dep]._get_target_files()
        return files

    def _deps_outputs(self):
        return list(self._implicit_dependencies())

    def _deps_generated_headers(self):
        files, dirs = set(), set()
        targets = self.blade.get_build_targets()
        for dkey in (self.expanded_deps or self.deps):
            dep = targets.get(dkey)
            if not dep:
                continue
            for hdr in dep.attr.get('generated_hdrs', []):
                files.add(hdr)
                dirs.add(os.path.dirname(hdr))
            for inc in dep.attr.get('generated_incs', []):
                dirs.add(inc)
        return files, dirs

    # --- edge emission ---

    def _rule_name(self):
        self._edge_seq += 1
        suffix = '' if self._edge_seq == 1 else '_%d' % self._edge_seq
        return '%s__rule__%s' % (
            regular_variable_name(self._source_file_path(self.name)), suffix)

    def _emit_shell_edge(self, command, cmd_bash, cmd_bat, inputs, outputs,
                         implicit_deps, variables, description):
        sel, kind, bash = gen_command.select_command(
            command or '', cmd_bash or '', cmd_bat or '')
        if not sel:
            self.error('run_shell needs one of command / cmd_bash / cmd_bat')
            return
        outputs = list(outputs) if outputs is not None else list(self._outputs)
        inputs = list(inputs) if inputs is not None else self._expand_srcs()
        out_names = self.attr['custom_attrs'].get('outs') or [os.path.basename(o) for o in outputs]
        expanded = gen_command.expand_vars(
            sel, bash=(kind == 'bash'),
            src_names=self.srcs, src_paths=inputs,
            out_names=out_names, out_paths=outputs,
            path=self.path, build_dir=self.build_dir, error=self.error,
            first_vars=False)  # $FIRST_* deprecated -- custom rules use $OUTS[0]/$SRCS[0]
        wrapped = gen_command.wrap_command(expanded, kind, bash, outputs,
                                           self.blade.get_root_dir())
        rule = self._rule_name()
        desc = console.colored('{} {}'.format(
            description or self.attr['description'], self.fullname), 'dimpurple')
        self._write_rule(_RULE_FORMAT % (rule, wrapped, desc))
        vars = dict(variables or {})
        if '${_in_1}' in wrapped and inputs:
            vars['_in_1'] = inputs[0]
        if '${_out_1}' in wrapped and outputs:
            vars['_out_1'] = outputs[0]
        self.generate_build(
            rule, outputs, inputs=inputs,
            implicit_deps=implicit_deps if implicit_deps is not None
            else self._implicit_dependencies(),
            variables=vars)

    def _emit_edge(self, rule, inputs, outputs, implicit_deps, variables):
        outputs = list(outputs) if outputs is not None else list(self._outputs)
        inputs = list(inputs) if inputs is not None else self._expand_srcs()
        self.generate_build(
            rule, outputs, inputs=inputs,
            implicit_deps=implicit_deps if implicit_deps is not None
            else self._implicit_dependencies(),
            variables=variables or {})

    # --- generation + fingerprint ---

    def generate(self):
        # Flush the edges recorded by the action (run in __init__); deps are
        # fully resolved by now, so implicit_deps / dep files are available.
        for flush in self._pending_edges:
            flush()

    def _fingerprint_entropy(self):
        entropy = dict(self.attr)
        entropy['custom_rule_action'] = self._action_fingerprint()
        entropy['custom_rule_schema'] = sorted(
            (k, a.kind, repr(a.default), a.mandatory, tuple(a.exts or ()))
            for k, a in self._schema.items())
        return entropy

    def _action_fingerprint(self):
        parts = []
        try:
            parts.append(inspect.getsource(self._action))
        except (OSError, TypeError):
            code = getattr(self._action, '__code__', None)
            parts.append(code.co_code.hex() if code else repr(self._action))
        try:
            src = inspect.getsourcefile(self._action)
            if src and os.path.exists(src):
                parts.append(md5sum_file(src))
        except (OSError, TypeError):
            pass
        return md5sum('\n'.join(parts))


def _default_of(spec):
    if spec.kind in _LIST_KINDS:
        return list(spec.default or [])
    return spec.default


def _coerce(spec, val, bad, name):
    """Coerce/validate a value to its declared kind; record (name, want) in
    ``bad`` on a type mismatch (reported via self.error after super().__init__)."""
    if spec.kind in _LIST_KINDS:
        return var_to_list(val)
    if spec.kind == 'bool':
        if not isinstance(val, bool):
            bad.append((name, 'a bool'))
        return bool(val)
    if spec.kind == 'int':
        if not isinstance(val, int) or isinstance(val, bool):
            bad.append((name, 'an int'))
            return spec.default
        return val
    if spec.kind == 'string':
        if not isinstance(val, str):
            bad.append((name, 'a string'))
            return str(val)
    return val


def define_rule(name, attrs=None, action=None, provides_cc=False, description='CUSTOM'):
    """Define a new rule type. ``.bld``-only (injected via extension globals).

    Returns the BUILD-callable rule function; bind it (``my_rule = define_rule(
    'my_rule', ...)``) so ``load`` can import it.
    """
    rule_type = name
    if action is None or not callable(action):
        console.fatal('define_rule("%s"): "action" must be a callable' % rule_type)
    schema = dict(attrs or {})
    for an, spec in schema.items():
        if not isinstance(spec, Attr):
            console.fatal('define_rule("%s"): attr "%s" must be attr.<kind>(...)' % (
                rule_type, an))

    def rule_fn(name, deps=None, visibility=None, tags=None, **kwargs):
        target = CustomRuleTarget(
            rule_type=rule_type, schema=schema, action=action,
            provides_cc=provides_cc, description=description,
            target_name=name, deps=deps,
            visibility=var_to_list_or_none(visibility), tags=tags,
            attr_values=kwargs)
        build_manager.instance.register_target(target)

    rule_fn.__name__ = rule_type
    return rule_fn


# `define_rule` and `attr` are top-level builtins ONLY in `.bld` extension files
# (absent from BUILD globals), which is what restricts define_rule to `.bld`.
build_rules.register_extension_variable('define_rule', define_rule)
build_rules.register_extension_variable('attr', attr)
