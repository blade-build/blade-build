# Dependency analysis and ninja file generation

After BUILD files are loaded and `Target` objects are registered, blade
turns the in-memory graph into a set of ninja files: one root
`build.ninja` plus per-target `<pkg>/<name>.build.ninja` files included
from it. Most of the implementation effort is in **not having to do all
that work every time** — both transitive-dep expansion and per-target
ninja generation are cached aggressively across the analysis phase and
across incremental rebuilds.

| File | Role |
| --- | --- |
| `src/blade/dependency_analyzer.py` | `expanded_deps`, topological sort, cycle detection |
| `src/blade/build_manager.py` | Orchestration; per-target fingerprint and ninja-file caching |
| `src/blade/backend.py` | Root-file header, global rules, helper templates |
| `src/blade/target.py` | `generate_build` / fingerprint computation |
| `src/blade/util.py` | `write_if_changed` |

## 1. Dependency graph

`Target.deps` is the **declared** dep list from the BUILD. Analysis fills
in `Target.expanded_deps`: the transitive, deduplicated, topologically
sound list a target actually needs.

- `_expand_target_deps()` recurses through `deps`, with a per-walk
  `root_targets` path set; revisiting an in-progress target raises a
  `Loop dependency` fatal that names the offending edge.
- `_unique_deps()` deduplicates while preserving order (keeping the last
  occurrence), so the relative position relevant to linking is not
  perturbed.
- The expanded list is **memoized on the target**: every consumer that
  asks for `target.expanded_deps` afterwards gets the cached value. The
  reverse direction (`expanded_dependents`) is filled in the same pass,
  for the few queries that need it.
- `_topological_sort()` runs Kahn's algorithm over the whole build graph.
  The output order is significant: when generating ninja code for a target,
  blade may need information already produced for its dependencies (for
  example, a `proto_library`'s declared generated headers must be visible
  before a `cc_library` that depends on it emits its include lines).

## 2. Per-target ninja generation

A target's `generate()` method (implemented per subclass) emits a sequence
of ninja `build` and `rule` statements via two helpers:

- `Target.generate_build(rule, outputs, inputs, ...)` constructs a `build`
  statement with `inputs`, `implicit_deps` (after `|`), `order_only_deps`
  (after `||`), `implicit_outputs`, and per-edge `variables`. The result
  is appended to the target's internal text buffer.
- `_NinjaFileHeaderGenerator.generate_rule(name, command, ...)` in
  `backend.py` declares a global rule (cc, cxx, ar, link, proto,
  cxxhdrs, ccincchk, ...) once, with all the conventional fields
  (`depfile`, `deps`, `restat`, `pool`, `rspfile`).

The text accumulated in the target buffer is written out to
`<build_dir>/<path>/<name>.build.ninja`. The root `build.ninja` then
plain-`include`s that file (no `subninja` — the per-target files are
fragments meant to share the global rules).

## 3. Root `build.ninja` structure

`_NinjaFileHeaderGenerator.generate()` emits the root file in a fixed order:

1. The minimum `ninja_required_version` line and `builddir = ...`.
2. Global pools (e.g. a `heavy_pool` with depth 1 to throttle a few rules
   that don't parallelize well).
3. All global ninja `rule` declarations — every compile/link/codegen rule
   the workspace might use, regardless of whether any specific target ends
   up needing them.
4. One-off build statements such as the SCM stamp.
5. An `include <path>.build.ninja` line per generated per-target file, in
   topological order (so deps come before dependents).

The two wrapper scripts referenced by compile rules (`cc_wrapper.sh` for
POSIX, `cc_wrapper.py` for MSVC) and the pickled
`inclusion_declaration.data` consumed by `ccincchk` are also written into
the build dir as a side effect of analysis, the first time anything
references them.

## 4. Incrementality

Three caching layers cooperate to avoid redoing work on each run:

**(a) Per-target fingerprint** —`Target.fingerprint()` is an MD5 over an
entropy dict that includes the blade revision, the config digest, srcs,
direct deps' fingerprints, the rule type, and the rule's `cmd`. Each
per-target ninja file starts with `#Fingerprint=<hash>` on line 1. Before
regenerating, `build_manager` reads the old fingerprint; if unchanged,
**the whole per-target file is reused as-is** and nothing else runs for
that target.

**(b) `write_if_changed`** in `util.py` — used for the cc wrappers, the
inclusion-declaration pickle, the per-target ninja files, and (inside the
cc wrappers themselves) for the `.incstk` files. It compares the new bytes
to the on-disk file and only writes when they differ, preserving mtime
otherwise. Ninja's `restat = 1` rule flag then uses that preserved mtime
to **prune downstream edges** whose only input was a now-unchanged
implicit output ([see hdrs check](hdrs_check.md) for the full chain
applied to `.incstk`).

**(c) The `expanded_deps` memoization** described above ensures the
transitive dependency walk runs once per target per analysis phase, not
once per consumer.

## 5. Implementation details and design notes

- **Topological order is for generation, not execution.** Ninja itself
  schedules executions purely from the graph. Blade sorts targets so it
  can compute fields that one target needs from another (e.g.
  `declared_genhdrs` propagated from `proto_library` to `cc_library`)
  before the consuming target emits its rules.
- **Order-only deps (`||`) for generated headers** are pervasive. They
  guarantee the generator runs before any compile that might `#include`
  the generated file, but they do **not** force a recompile if only the
  generator's outputs' timestamps moved. Combined with `restat` on the
  generator's rule, this gives "regenerated but unchanged → no rebuild"
  semantics. The compiler depfile (`-MMD`) handles actual content-level
  re-triggering.
- **Per-target fingerprint covers exactly the load-phase inputs.** Targets
  with the same fingerprint produce the same `.build.ninja` text, by
  construction, so reusing the file is safe. Things that don't affect
  load-phase output (such as `cc_test` execution flags) deliberately
  aren't in the fingerprint.
- **Targets outside the requested set still get ninja rules.** Blade
  needs them because they may be transitive deps of requested targets;
  `--no-test` and `--generate-package` are the explicit knobs that filter
  out test/package targets that would otherwise be pulled in.
- **`pool = heavy_pool`** with `depth = 1` is the simplest answer to a few
  rules whose tools (link-with-LTO, big proto codegen, ...) don't tolerate
  high parallelism well — they are routed through a 1-wide pool so ninja
  serializes them automatically.
- **The inclusion check uses the same caching plumbing.** The `ccincchk`
  rule's only inputs are `.incstk` implicit outputs of compile rules.
  Because `write_if_changed` preserves the `.incstk` mtime when the
  inclusion stack didn't actually change, ninja's `restat` skips the
  check on recompiles that didn't alter `#include`s — a substantial perf
  win on incremental builds.

## 6. UX optimizations

- **Memoize once, query many.** `expanded_deps` and `expanded_dependents`
  are computed in a single pass and reused by every downstream consumer.
  The cost of "what does this depend on?" goes from O(graph) per query
  to O(1).
- **`write_if_changed` everywhere.** Per-target ninja files,
  inclusion-stack files, wrapper scripts, the inclusion-declaration
  pickle — all only touch disk when the bytes change. Combined with
  ninja's `restat`, this pushes the granularity of "did anything change?"
  from "the file was rewritten" down to "the file's contents differ".
- **Per-target ninja files survive identical regenerations.** A no-op
  edit (whitespace, comment) to a BUILD file that doesn't move the
  fingerprint costs nothing past the load phase.
- **Failures point at the cause.** `Loop dependency` reports the
  offending edge and walks the cycle; missing-dep failures in the hdrs
  check show the inclusion stack; topological-sort failures (rare) name
  the unresolved input. The investment in legible diagnostics here is
  deliberate, because a bad message on a many-thousand-target graph is
  hard to debug.
