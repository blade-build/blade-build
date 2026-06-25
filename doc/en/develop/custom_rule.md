# How Custom Rules (`define_rule`) Work

`define_rule` lets a `.bld` extension declare a **new rule type** — typed
attributes plus a Python *action* that declares outputs and emits build edges —
without touching Blade's core. This document explains **how it is implemented**;
for the user-facing API see [build_rules/custom_rule.md](../build_rules/custom_rule.md).

It is an [experimental](https://github.com/blade-build/blade-build/issues/829)
feature; the API may still change.

Source files involved:

| File | Responsibility |
| --- | --- |
| `src/blade/custom_rule_target.py` | The whole feature: the `attr` namespace, the `ActionContext` / `_Actions` passed to an action, the generic `CustomRuleTarget`, and the `define_rule` builtin |
| `src/blade/build_rules.py` | `register_extension_variable` — makes `define_rule` / `attr` visible **only in `.bld` files** |
| `src/blade/gen_command.py` | Command-template expansion (`$SRCS` / `$OUTS` / …) and platform selection, shared with `gen_rule` |
| `src/blade/rule_registry.py` | `register_rule_provider` — the shared-ninja-rule slot a `ctx.actions.shared_rule` writes into |
| `src/blade/cc_targets.py` | `declare_hdrs` / `declare_hdr_dir` — how a `provides_cc` rule's generated headers flow to `cc_*` deps |

---

## 1. Why a rule, not a macro

A [macro](../build_rules/extension.md) — a plain function in a `.bld` that calls
existing rules — covers simple reuse, but it cannot *declare new outputs that
other targets see during analysis*. A `cc_library` that depends on a code
generator needs the generated header to exist as a declared output **before** its
own `generate()` runs, so the header is visible to the inclusion check and the
include path. `define_rule` is the mechanism for that: it is modeled on
[Bazel's rules](https://bazel.build/extending/rules) but intentionally smaller —
one `action`, no provider system beyond the `cc_*` header flow.

## 2. `.bld`-only visibility

`define_rule` and `attr` are **not** in the BUILD-file globals. They are
registered as *extension* variables:

```python
build_rules.register_extension_variable('define_rule', define_rule)
build_rules.register_extension_variable('attr', attr)
```

`build_rules.get_all_for_extension()` injects these into the globals of a `.bld`
loaded via `load`, and nowhere else. That single registration site is the entire
enforcement of "custom rules can only be defined in extensions" — a BUILD file
that names `define_rule` simply gets a `NameError`. The function `define_rule`
returns is an ordinary callable, so once `load`-ed it is called from BUILD like
any native rule.

## 3. The attribute schema (`attr`)

`attr` is a singleton `_AttrNamespace`; each method (`attr.string`, `attr.bool`,
`attr.int`, `attr.string_list`, `attr.src_list`, `attr.dep_list`, `attr.out_list`)
returns a small serializable `Attr` (`kind`, `default`, `mandatory`, `exts`).
`Attr` deliberately holds **no callables or rich objects** — only the kind
string, a plain default, and bools — so the schema can go straight into the
target's fingerprint (see §7) without un-hashable entropy.

Two kinds are special-cased at construction because they feed Blade's own target
fields rather than the action's `ctx.attrs`:

- `src_list` → spliced into the target's `srcs` (with optional extension
  filtering via `exts`).
- `dep_list` → merged into the target's `deps`.

Everything else lands in `ctx.attrs[name]`. `name` / `deps` / `visibility` /
`tags` are always available and need not be declared.

## 4. The target: `CustomRuleTarget`

`define_rule` returns a thin `rule_fn(name, deps, visibility, tags, **kwargs)`
that constructs one `CustomRuleTarget` per BUILD invocation and registers it with
`build_manager.instance.register_target()`.

`CustomRuleTarget.__init__` does the schema work:

1. For each declared attribute, pop the supplied value (or take the default),
   record a **missing-mandatory** error, and `_coerce` it to the declared kind —
   recording a **type-mismatch** error rather than raising, so all schema
   problems surface together after `super().__init__`.
2. Route `src_list` / `dep_list` into `srcs` / `deps`; the rest into a `custom`
   dict stored as `self.attr['custom_attrs']`.
3. Anything left in `attr_values` is an **unknown attribute** → error.
4. The target type is `'custom:' + rule_type`, and it is tagged
   `type:custom_rule`.

## 5. The action runs in the analysis phase

The crucial design choice mirrors Bazel: **the action runs at construction
time** (still the analysis phase), not at `generate()`:

```python
self._action(ActionContext(self))      # in __init__
if not self._outputs:
    self.error('custom rule "%s" action declared no outputs' % rule_type)
```

Why now: an action's `declare_header` / `declare_inc_dir` must register the
generated header into the `cc_*` header maps **before** any dependent target
generates — exactly as `gen_rule` and `proto_library` do. So the action is split
in two:

- **Output declaration happens immediately.** `ctx.declare_output(name)` appends
  to `self._outputs` and registers the file under an index label via
  `_add_target_file`. `ctx.declare_header` additionally calls
  `cc_targets.declare_hdrs(self, [name])` and records `generated_hdrs`;
  `ctx.declare_inc_dir` calls `declare_hdr_dir` and records
  `generated_incs` / `export_incs` — but only when the rule was defined with
  `provides_cc=True`.
- **Build edges are only *recorded* now, flushed later.** `ctx.actions.run_shell`
  / `ctx.actions.run` append a `functools.partial` to `self._pending_edges`
  instead of emitting immediately, because the dep graph is not fully resolved
  during construction. `generate()` then replays them:

  ```python
  def generate(self):
      for flush in self._pending_edges:
          flush()
  ```

  By `generate()` time `expanded_deps` and the dep output files are available, so
  `implicit_deps` resolves correctly.

`ActionContext` exposes the read side (`ctx.name`, `ctx.attrs`, `ctx.toolchain`,
`ctx.config(section)`, `ctx.deps_outputs()`,
`ctx.deps_generated_headers()`); `_Actions` (`ctx.actions`) the emit side.

## 6. Edge emission reuses the `gen_rule` machinery

`_emit_shell_edge` is the heart of `run_shell` and is deliberately the same
pipeline `gen_rule` uses:

1. `gen_command.select_command(command, cmd_bash, cmd_bat)` picks the platform
   variant (generic host shell vs bash vs bat).
2. `gen_command.expand_vars(...)` expands `$SRCS` / `$OUTS` / `$OUTS[i]` /
   `$SRC_DIR` / `$OUT_DIR` / `$BUILD_DIR`. **`first_vars=False`** here, so the
   deprecated `$FIRST_SRC` / `$FIRST_OUT` are *not* available — custom rules use
   `$SRCS[0]` / `$OUTS[0]`.
3. `gen_command.wrap_command(...)` wraps it for the chosen shell.
4. A uniquely-named per-target ninja rule is written (`_rule_name()` adds a
   sequence suffix so multiple edges in one action don't collide), then
   `generate_build(...)` emits the build edge. `outputs` defaults to all
   outputs declared so far; `inputs` to the expanded `srcs`.

`ctx.actions.shared_rule(ninja_rule)` is the alternative for many edges sharing
one rule: it registers the rule **once** into the registry's custom slot
(`rule_registry.register_rule_provider(..., name='custom:'+ninja_rule.name)`,
idempotent by name), and `ctx.actions.run(rule, ...)` emits edges that reference
it via `_emit_edge`.

## 7. Fingerprinting — why the action must be self-contained

A target's fingerprint decides incremental rebuilds. `CustomRuleTarget`
extends `_fingerprint_entropy` with both the schema and the **action's source**:

```python
entropy['custom_rule_action'] = self._action_fingerprint()
entropy['custom_rule_schema'] = sorted(
    (k, a.kind, repr(a.default), a.mandatory, tuple(a.exts or ())) ...)
```

`_action_fingerprint` hashes `inspect.getsource(self._action)` plus the md5 of
the action's defining file. This is why the V1 limitation **"keep the action
self-contained in its `.bld`"** exists: helpers the action imports from other
`.py` modules are *not* part of this fingerprint, so editing them would not force
a rebuild. The schema is serializable precisely so it can join the entropy here
without special handling.

## 8. Limitations that fall out of the design

- **`.bld`-only** — a direct consequence of §2 (the builtins aren't in BUILD
  globals).
- **No general providers** — cross-rule data is limited to the
  `generated_hdrs` / `generated_incs` flow of §5, because that is the only
  channel wired into `cc_*` consumption.
- **Self-contained action** — see §7.
- **Generated headers resolve after system/SDK paths**, so an output name that
  collides with a system header is shadowed; the rule cannot reorder include
  paths.
