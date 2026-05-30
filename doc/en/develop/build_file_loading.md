# How BUILD files are discovered, loaded, and registered

Blade does not pre-scan the whole workspace. Starting from the targets you
asked for, it discovers exactly the BUILD files it needs, `exec()`s them in
a restricted namespace, and follows their declared `deps` to pull in more
BUILDs until the reachable set is closed. This keeps load time
proportional to the part of the workspace actually involved.

| File | Role |
| --- | --- |
| `src/blade/target_pattern.py` | Normalize CLI specs into canonical `path:name` keys |
| `src/blade/load_build_files.py` | Discover, exec, sandbox, BFS-follow deps |
| `src/blade/build_rules.py` | The set of names callable in a BUILD file |
| `src/blade/build_manager.py` | Singleton holding the target database, key conflict detection |
| `src/blade/target.py` | `Target` base class, source-location capture |

## 1. From command-line pattern to BUILD-file set

The user can ask for `//foo/bar:lib`, `foo/bar`, or `//foo/bar/...`.
`target_pattern.normalize()` rewrites all three into a canonical
`<path>:<name>` form: a bare directory becomes `<dir>:*` (all targets in
that BUILD), and `<dir>/...` becomes `<dir>/...:...` (the recursive
marker).

`_expand_target_patterns()` then turns these patterns into a set of starting
BUILD files:

- `path:name` records `path:name` as a direct target; only that package's
  BUILD is loaded.
- `path:*` adds `path` to `starting_dirs`.
- `path/...` walks the directory tree with `os.walk()` and collects every
  directory containing a `BUILD` file, honouring two boundary markers:
  - `.bladeskip` — skip this subtree entirely.
  - A nested `BLADE_ROOT` — never cross into another workspace.

This recursive walk is the only place the file system is enumerated;
everything else discovers BUILD files by following `deps` edges.

## 2. Loading: `exec()` with restricted globals

Each BUILD file is a Python script. It is executed via `exec_file(path,
globals_dict, None)`. The globals are built fresh per file by
`_get_globals_for_build_file()`:

- All registered rule names (`cc_library`, `proto_library`, `gen_rule`, ...)
  injected from `build_rules.get_all()`.
- The `blade` module (`dsl_api.get_blade_module()`) — see
  [Built-in functions and the `blade.*` DSL](dsl_api.md).
- Optionally `__builtins__ = restricted.safe_builtins` when
  `global_config.restricted_dsl` is on (default true), which removes
  `__import__`, `exec`, `eval`, narrows `open()` to read-only, etc.

There is **no parameter that tells a BUILD file its own path**. Instead, a
process-wide `build_manager.instance` exposes
`get_current_source_path()`, which is set and restored around each
`exec_file()` call. When a rule function runs inside the BUILD, it reads
this to form its target key (`<path>:<name>`). The source location for
diagnostics is captured at the same time, so any error in a BUILD points to
the exact file and line in the user's code rather than internal blade
frames — a deliberate UX choice.

## 3. Target registration and the key namespace

When `cc_library(name='x', ...)` runs, the rule constructs a `Target`,
which on its way through `__init__` calls
`build_manager.instance.register_target(self)`. That singleton holds a
single `__target_database` dict keyed by `<path>:<name>`. Duplicate keys
fail fatally **at load time**, with the source locations of both definitions
in the message — cheaper to diagnose than at build time, and impossible to
miss.

System-library deps such as `#dl` are normalized to the pseudo-key `#:dl`
so they share the same address space without colliding with anything in a
real `path` (any path with `#` is illegal).

## 4. Iterative deps-following (lazy loading)

After the starting BUILDs are loaded, `_load_related_build_files()` runs a
BFS over the deps graph:

- Pop a target key from a queue, load its BUILD file (if not already
  loaded), enqueue each of its `deps` that haven't been visited.
- A `processed_dirs` dict short-circuits any directory already loaded
  (success or failure), so each BUILD file is `exec`'d at most once per
  invocation.
- Targets whose paths fall under `.bladeskip` or another nested
  `BLADE_ROOT` are dropped with a diagnostic — they cannot be reached even
  if some other BUILD references them.

Cycle detection comes later, in `dependency_analyzer._expand_target_deps()`:
during the recursion it maintains a path set; revisiting an in-progress
target is reported as a `Loop dependency` fatal with the offending edge
named.

## 5. Globs and `load()`

- `glob(include, exclude, allow_empty=False)` uses `pathlib.Path.glob()`
  relative to the BUILD's own directory. `**` is supported. Excludes are
  filtered in a second pass — exact strings via set membership for speed,
  patterns via `path.match()`. `allow_empty=True` is the explicit opt-in
  for "I know this might match nothing" cases, so unintended empty matches
  remain a warning by default.
- `load('//path:ext.bld', sym1, sym2)` exposes named symbols from an
  extension file. The result is cached per absolute extension path in
  `__loaded_extension_info`, so multiple BUILDs `load()`ing the same
  extension `exec` it only once.

## 6. UX optimizations

- **Lazy loading by deps closure** keeps load time roughly proportional to
  the slice of the workspace involved. On large monorepos this is the main
  reason `blade build //foo:bar` doesn't have to read every BUILD file.
- **BUILD-file dedup via `processed_dirs`** turns a potentially exponential
  BFS into linear work, since every BUILD is loaded once per `blade`
  invocation regardless of how many edges point into it.
- **Extension caching via `__loaded_extension_info`** is the same idea one
  level down: `load()`'d files are `exec`'d once even if referenced by many
  BUILDs.
- **Per-target fingerprint** (recorded as `#Fingerprint=...` on line 1 of
  the per-target `.build.ninja`) lets incremental rebuilds skip
  ninja-file regeneration entirely when a target's load-phase inputs
  (srcs, deps, config digest, blade revision) haven't changed. See
  [dependency analysis & ninja generation](dependency_analysis.md).
- **Errors pin to BUILD source location.** Each `Target` records the BUILD
  file path and line number at construction; diagnostics (missing dep,
  unknown attribute, duplicate name, ...) report in `BUILD:lineno: error:`
  form, which most editors turn into clickable jumps. This is one of the
  most visible "developer ergonomics" investments in blade.
- **`.bladeskip` / nested `BLADE_ROOT`** lets a workspace carve out parts
  of the tree (vendored sources, scratch directories) that the recursive
  walk must ignore, without rewriting BUILDs to use explicit deps. They
  apply both to the initial `...` expansion and to the BFS deps walk.
