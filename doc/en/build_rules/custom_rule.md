# Custom Rules (`define_rule`)

> **Experimental.** The API (`define_rule` / `attr` / the action `ctx`) may change
> in a future release. Tracked in [#829](https://github.com/blade-build/blade-build/issues/829).

A [macro](extension.md) (a plain function in a `.bld` that calls existing rules
like `gen_rule`) is enough for simple reuse. When you need a **real new rule
type** — with typed attributes and a Python *action* that computes outputs and
emits build commands — use `define_rule`. It is inspired by
[Bazel's rules](https://bazel.build/extending/rules) but intentionally smaller.

## Quick example

Suppose you've created an *awesome* language whose compiler, `awesomec`, generates C++.

`//myrules/awesome.bld`:

```python
def _impl(ctx):
    out = ctx.declare_output(ctx.name + '.cc')          # declare an output
    if ctx.attrs['gen_header']:
        ctx.declare_header(ctx.name + '.h')             # a header cc_* can use
    ctx.actions.run_shell(command='awesomec $SRCS -o $OUTS', outputs=[out])

awesome_library = define_rule(
    name='awesome_library',
    attrs={
        'srcs': attr.src_list(exts=['awesome']),
        'opt':  attr.string(default='-O2'),
        'gen_header': attr.bool(default=True),
    },
    provides_cc=True,
    action=_impl,
)
```

`//demo/BUILD`:

```python
load('//myrules/awesome.bld', 'awesome_library')

awesome_library(name='demo', srcs=['demo.awesome'])
cc_binary(name='app', srcs=['main.cc'], deps=[':demo'])   # gets demo.h / demo.cc
```

## `define_rule`

`define_rule` is a **builtin available only in `.bld` extension files** (like
`attr`; neither is visible in `BUILD` files). Bind its result to a name so
`load` can import it: `awesome_library = define_rule('awesome_library', ...)`.

```python
define_rule(name, attrs=None, action=None, provides_cc=False, description='CUSTOM')
```

- `name`: str, the rule type / generated BUILD function name.
- `attrs`: dict, attribute name → `attr.<kind>(...)` (see below). `name`, `deps`,
  `visibility`, `tags` are always available and need not be declared.
- `action`: callable `action(ctx)` — run in the analysis phase to declare
  outputs and register build edges (see *The action*). Required.
- `provides_cc`: bool, if True the headers/include dirs declared by the action
  flow to dependent `cc_*` targets (via `generated_hdrs` / `generated_incs`).
- `description`: str, default progress label for emitted edges.

## Attributes (`attr`)

| kind | value | notes |
|---|---|---|
| `attr.string(default='', mandatory=False)` | str | |
| `attr.bool(default=False)` | bool | |
| `attr.int(default=0)` | int | |
| `attr.string_list(default=())` | list[str] | |
| `attr.src_list(default=(), exts=None)` | list[str] | becomes the rule's `srcs`; `exts` restricts file extensions |
| `attr.dep_list(default=())` | list[str] | merged into the rule's `deps` |
| `attr.out_list(default=())` | list[str] | a list of output names (the action declares them) |

`mandatory=True` makes an attribute required. Unknown attributes, missing
mandatory ones, and type mismatches are reported as errors.

## The action

`action(ctx)` runs in the **analysis phase** (when the BUILD is loaded): it only
*declares outputs* and *registers build edges* — it never runs commands or reads
/ writes files (that happens later, during the build). Declaring outputs in this
phase is what lets dependents see a rule's generated headers.

`ctx` read state:

- `ctx.name`, `ctx.path`, `ctx.fullname`, `ctx.build_dir`, `ctx.target_dir`
- `ctx.attrs` — the validated attribute values (`src_list` already path-expanded)
- `ctx.toolchain`, `ctx.config(section)`
- `ctx.deps_outputs()` — output files of the rule's deps
- `ctx.deps_generated_headers()` — `(files, dirs)` of generated headers from deps

`ctx` output declaration:

- `ctx.declare_output(name)` → returns the full path of an output file
- `ctx.declare_header(name)` → like `declare_output`, and (when `provides_cc`)
  exposes the header to dependent `cc_*` targets
- `ctx.declare_inc_dir(inc)` → expose a generated include directory to dependents

`ctx.actions` — emit build edges:

- `ctx.actions.run_shell(command=None, cmd_bash=None, cmd_bat=None, inputs=None,
  outputs=None, implicit_deps=None, variables=None, description=None)` — emit a
  per-target rule + build edge. `command` is the generic form (host shell);
  `cmd_bash` / `cmd_bat` are optional platform variants (selected like
  [`gen_rule`](gen_rule.md)). The command may use `$SRCS`, `$OUTS`,
  `$OUTS[i]` / `$SRCS[i]` (by index or name), `$SRC_DIR`, `$OUT_DIR`,
  `$BUILD_DIR`. (The deprecated `$FIRST_SRC` / `$FIRST_OUT` are **not** supported
  here — use `$OUTS[0]` / `$SRCS[0]`.) `outputs` defaults to all outputs declared
  so far; `inputs` to the rule's `srcs`.
- `ctx.actions.run(rule, inputs=None, outputs=None, …)` — emit a build edge that
  references a shared rule registered with `shared_rule`.
- `ctx.actions.shared_rule(ninja_rule)` — register one shared ninja rule
  (`blade.ninja_rule.NinjaRule`) once, so many edges/targets can reference it.

## Limitations (V1)

- `define_rule` works only in `.bld` files loaded via `load` — not in `BUILD`.
- The per-target build cache keys on the action's source and its `.bld` file, so
  **keep the action self-contained in its `.bld`**; helpers imported from other
  `.py` modules are not tracked.
- No general provider mechanism yet — cross-rule data is limited to the
  `generated_hdrs` / `generated_incs` flow to `cc_*` targets.
- Generated headers are searched after system/SDK include paths, so avoid output
  names that collide with system headers.
