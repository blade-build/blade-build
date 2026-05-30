# `gen_rule`: custom build steps and how other targets see them

`gen_rule` lets a BUILD file run an arbitrary shell command and declare
its outputs. The interesting part isn't the rule itself — it's how those
outputs become first-class inputs to other targets without an explicit
"this is a generated file" annotation everywhere.

| File | Role |
| --- | --- |
| `src/blade/gen_rule_target.py` | `GenRule` class, attribute validation, cmd substitution |
| `src/blade/target.py` | `_target_file_path()` (where outputs live) |
| `src/blade/cc_targets.py` | Auto-discovery of gen_rule outputs in `srcs`/`hdrs` |

## 1. Attributes and `cmd` substitution

```python
gen_rule(
    name = 'codegen',
    srcs = ['schema.idl'],
    outs = ['schema.h', 'schema.cc'],
    cmd  = '$TOOL --in=$FIRST_SRC --out-dir=$OUT_DIR',
    deps = ['//tools:my_codegen'],
    generated_hdrs = ['schema.h'],   # optional; auto-inferred from outs
)
```

- `outs` is required; entries are normalized paths relative to the
  package, and `..` is rejected (no escape from the build dir).
- `cmd` is stored as a template and expanded at ninja-generation time.
  Substitutions:
  - `$SRCS` / `$OUTS` — all inputs/outputs (ninja's `${in}`/`${out}`).
  - `$FIRST_SRC` / `$FIRST_OUT` — the first input/output as separate
    per-edge ninja variables, so a tool that takes a single
    input/output doesn't have to deal with list joining.
  - `$SRC_DIR` — the source package path.
  - `$OUT_DIR` — `build_dir/<pkg>` (where outputs land).
  - `$BUILD_DIR` — the workspace's build root.
  - `$(location //pkg:target)` — resolved to the named target's output
    file path. This is how a gen_rule reaches another target's
    generated artifact.
- `generated_hdrs` (optional) names the outputs that should be treated
  as headers for visibility purposes; if omitted, blade infers them from
  output extensions.
- `generated_incs` (optional) lists directories to add to consumers'
  include path — useful for generators that produce a tree of headers
  the consumer should `#include` by sub-path.

## 2. Ninja generation

Each `gen_rule` declares its **own** ninja rule (not a shared
`gen_rule` rule). The rule name is derived from the target key, and the
emitted template includes a trailing `ls ${out} > /dev/null` check so
that a command which silently fails to produce its declared outputs is
caught immediately, not later when a consumer references a missing
file.

Outputs land at `build_dir/<pkg>/<outname>` via
`_target_file_path()`, which is the only path-construction path; there
is no way to write outputs under the source tree. This is enforced by
design — `gen_rule` never receives a source-relative output path.

The command runs through `/bin/sh` on POSIX (and respects the
workspace's CWD, so paths are workspace-relative). Users who need
Windows-specific commands write them with that in mind; blade does not
attempt to translate `/bin/sh` semantics to `cmd.exe`.

## 3. How other targets see the outputs

The key piece is **auto-discovery**: a `cc_library` that lists
`schema.cc` in its `srcs` doesn't need to declare a dep on the
`codegen` target. When `cc_targets._cc_objects()` (and other consumers)
walk `srcs`, each entry that does not exist in the source tree is
resolved as a generated file by querying `_target_file_path()` for the
target that produces it. The dep edge is added implicitly.

Generated headers go further:

- `gen_rule.generated_hdrs` / `generated_incs` are registered into the
  same global maps used by `declare_hdrs()` / `declare_hdr_dir()`, so
  the [hdrs check](hdrs_check.md) knows the header's owning target.
- Consumers' `declared_genhdrs` and `declared_genincs` are filled by
  walking `expanded_deps` and collecting each dep's
  generated-header declarations. This is the transitive visibility the
  check needs.
- The generated headers are added as **order-only deps** (`||`) of the
  compile, so they are guaranteed to exist before any compile runs but
  do not retrigger recompilation just because their mtime changed.

The combination of the four (`-Ibuild_dir`, auto-discovery in `srcs`,
generated-header declaration, order-only deps) is what makes "a
gen_rule looks like a normal source to its consumers" work end to end.

## 4. Implementation details and UX optimizations

- **The `ls ${out}` check is the safety net.** It catches the case
  where a user's `cmd` accidentally writes to a different filename than
  declared in `outs`, or silently fails. Without it, downstream
  consumers would fail with "no such file" errors that are much harder
  to trace.
- **Source tree stays clean by construction.** Because outputs are
  always rooted at `build_dir/<pkg>/`, a gen_rule cannot pollute the
  source tree. This is one less rule for users to learn.
- **Order-only + `restat` interact well.** If a gen_rule's outputs are
  byte-identical to last build (regeneration with the same input
  produced the same output), ninja's `restat` on the producing rule
  preserves the mtime and the order-only dep does not force a downstream
  recompile. Combined with `write_if_changed`-like tools, this lets a
  no-op codegen pass cost nothing.
- **`$(location //pkg:target)` is the disciplined way to call other
  generators.** It resolves at ninja-generation time so the path is
  correct regardless of where the producing target lives in the tree;
  hard-coding `build64_release/...` paths in a `cmd` is brittle.
- **Generated-header visibility is the same machinery as proto.** A
  gen_rule that produces `.h` files registers them via the same paths
  proto targets use, so the [hdrs check](hdrs_check.md) treats them
  uniformly — there is no second pathway to maintain.
- **Auto-discovery has one caveat.** If two gen_rules produce files
  with the same name in the same package, the auto-discovery is
  ambiguous; declaring the producing target explicitly via `deps`
  resolves it. The check that catches this is the same per-key
  uniqueness check used elsewhere.
- **Error reporting names the gen_rule target.** Failures of the
  `cmd` come from the underlying shell, but blade prefixes them with
  the target fullname and a description (default `COMMAND`) so a wall
  of parallel-build output is greppable for "which gen_rule failed?".
