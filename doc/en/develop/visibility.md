# How target visibility is implemented and enforced

Visibility restricts which targets are allowed to depend on a given
target. Blade stores each target's permissible-callers set as a small
collection of normalized patterns and checks every dep edge against it
during the dependency-analysis phase — once per build, not at runtime.

| File | Role |
| --- | --- |
| `src/blade/target.py` | `_init_visibility`, `_check_visibility`, `_match_visibility` |
| `src/blade/target_pattern.py` | `normalize`, `match` for pattern strings |
| `src/blade/dependency_analyzer.py` | Driving the per-edge check during analysis |
| `src/blade/config.py` | `global_config.default_visibility`, `legacy_public_targets` |

## 1. Attribute shape and defaults

`visibility` accepts:

- `'PUBLIC'` or `['PUBLIC']` — visible globally.
- An explicit list of target patterns: `['//path:target', ':sibling',
  '//path:*', '//path/...']`.
- `[]` — private to the BUILD file the target was defined in.
- `None` (omitted) — falls back to defaults, see below.

When `visibility` is omitted, the resolution is:

1. If the target's key appears in `global_config.legacy_public_targets`,
   treat as `{'PUBLIC'}`. This is the migration ramp for projects that
   used to default everything to public.
2. Otherwise use `global_config.default_visibility`, which itself
   defaults to an empty set (private). Blade 2.0+ made private the
   default; the `legacy_public_targets` list is the explicit knob for
   keeping the previous behaviour on a per-target basis while the
   project is being audited.

`target._visibility` is the normalized set actually consulted by the
check. `_visibility_is_default` records whether the user wrote
`visibility=` explicitly — used only to make diagnostics clearer
("defaults to private, see the docs").

## 2. Normalization

`_init_visibility()` walks each pattern through
`target_pattern.normalize(v, self.path)`:

- `'//foo:bar'` → `'foo:bar'`
- `':sibling'` → `'<current_path>:sibling'` (the current BUILD's
  package)
- `'//foo:*'` → `'foo:*'` (every target in `foo/`)
- `'//foo/...'` → `'foo:...'` (every target in `foo/` recursively)

`'PUBLIC'` is treated as a sentinel and stored as-is; no other
normalization is applied. The result is a `set[str]` — small,
hashable, and cheap to test against.

## 3. Enforcement: when and where

The check runs once per build, during `dependency_analyzer.analyze_deps()`,
right after deps are expanded. For each direct edge `A -> B`,
`_check_visibility(A, B)` evaluates `_match_visibility(A, B)`:

1. **Same package?** If `A.path == B.path`, allow. Targets sharing a
   BUILD file are always visible to each other — that's the smallest
   unit of "I clearly know what I'm doing."
2. **`'PUBLIC'` in B's set?** Allow.
3. **Exact key in B's set?** (`A.key in B._visibility`) Allow.
4. **Pattern match?** Iterate patterns; `target_pattern.match(A.key, p)`
   handles `:*` and `:...` wildcards. Match → allow.

If none match, the check reports:

```
<source location of A>: error: <A>: Not allowed to depend on "//<B>"
                              because of its visibility,
<source location of B>: info: which is declared here
```

If B's visibility defaulted to private, the diagnostic adds the "no
explicit visibility declaration, defaults to private, see the docs"
hint, since that's the case where a user is most likely to be confused
about why something they wrote is hidden.

The cost is O(deps × patterns). Visibility sets are tiny in practice
(usually one to three patterns) and matching is set-membership plus a
short iteration — no caching is needed.

## 4. Special cases and bypasses

- **Same-package targets** bypass visibility entirely. This is the
  rule that lets `cc_test` reach a sibling library's private internals
  without per-test exemptions — they're in the same BUILD, so the
  check is effectively a no-op.
- **System libraries** (`#dl`, `#pthread`, ...) are constructed with
  `visibility=['PUBLIC']` hard-coded, so they're always reachable.
- **Implicit dependencies** (gtest auto-injected into `cc_test`, SCM
  stamp, ...) are added through `_add_implicit_library` and go into the
  normal deps list. They are **not** bypassed; the implicit dep
  library still has to have appropriate visibility, otherwise the
  injection would silently fail every build. In practice these libs
  are `PUBLIC` by convention.
- **Prebuilt and foreign cc libraries** use the standard mechanism —
  no special path.
- **Unloaded targets are not checked.** Lazy BUILD loading means a
  workspace can have visibility-restricted targets that never get
  examined because nothing in the requested set reaches them. This is
  by design: the analysis only runs on the closure of what's being
  built.

## 5. Implementation details and UX optimizations

- **Private by default since 2.0**, plus a `legacy_public_targets` ramp.
  This is the kind of change you can't push to a large monorepo
  overnight; the ramp lets a project flip the default per-target as it
  audits, rather than having to convert everything at once.
- **`':...'` recursive patterns are evaluated by string match, not by
  walking the target tree.** They're cheap (one prefix comparison) and
  do the right thing because target keys are canonicalized to
  `<path>:<name>` early.
- **Diagnostics carry both endpoints.** Failures point at A's BUILD
  line (where the dep was declared) **and** at B's BUILD line (where
  the visibility was declared). Users don't have to bounce between
  files to figure out what's wrong.
- **No memoization of match results.** The check runs once per analysis
  phase and the patterns are simple, so caching would add code without
  saving time. If the suite grew, the cache would be a one-liner over
  `(A.key, frozenset(B._visibility))`.
- **Same-package bypass is the most-used implicit rule.** It is why a
  lot of BUILD files have no `visibility=` at all: the targets that
  need to talk to each other are siblings, and the same-package rule
  makes it work without any declaration. Visibility only comes into
  play when an outside package wants in.
- **Visibility is enforced, not used for filtering.** Blade does not
  drop a forbidden dep from the graph; it reports an error and stops.
  This is intentional — silently elide would mask actual bugs (a typo
  in `deps` looking like "the lib is hidden from me").
