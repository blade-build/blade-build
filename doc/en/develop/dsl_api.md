# Built-in functions and the `blade.*` DSL

A BUILD file is a Python script run inside a tightly-controlled namespace.
Two things live in that namespace: the **rule functions** (`cc_library`,
`proto_library`, ...) and an injected `blade` module that exposes the small
set of helpers a BUILD file may legitimately need (path manipulation,
config lookup, logging, environment introspection). Everything else from
the host Python is either absent or replaced with a safer counterpart.

| File | Role |
| --- | --- |
| `src/blade/build_rules.py` | The rule registry (`register_function`, `get_all`) |
| `src/blade/dsl_api.py` | The `blade` module exposed to BUILD files |
| `src/blade/restricted.py` | The safe builtins set (`safe_builtins`) |
| `src/blade/blade_types.py` | Shared rule-arg type aliases |
| `src/blade/util.py` | `var_to_list` / `var_to_list_or_none` normalizers |

## 1. Rule registration

Every rule type (`cc_library`, `cc_binary`, `py_library`,
`proto_library`, `gen_rule`, ...) is just a Python function defined in some
`*_targets.py` module. At module-import time, the file calls
`build_rules.register_function(cc_library)` etc., depositing the name in a
single global registry.

The registry is filled once per `blade` invocation by `_load_build_rules()`,
which imports the language modules in a fixed order. After that,
`build_rules.get_all()` returns the flat dict that becomes the basis of
every BUILD file's globals (see [BUILD file loading](build_file_loading.md)).

A "native" wrapper object built from the same dict is also stored, so
extensions loaded via `load()` can reach the rules as `native.cc_library`
even though `cc_library` itself isn't a global in extension scope (where it
shouldn't shadow user-defined functions). This split (BUILD ↔ extension)
keeps the surface of an extension small without taking the rules away from
extensions that genuinely need to call them.

## 2. The `blade` module

`dsl_api.get_blade_module()` constructs a small module-like object once per
BUILD load. It exposes:

- **`blade.config`** — `get_item(section, item)` and `get_section(name)`,
  the same getters described in [configuration](configuration.md).
- **`blade.console`** — `debug` / `info` / `notice` / `warning` / `error`
  routed through blade's normal diagnostic plumbing, so messages from a
  BUILD file get the same formatting and source-location prefix as any
  other blade output.
- **`blade.path`** — a curated subset of `os.path` (`abspath`, `basename`,
  `dirname`, `exists`, `join`, `normpath`, `relpath`, `splitext`). The
  *unsafe* `os.path` members (anything that could mutate or stat outside
  the workspace by accident) are not exposed.
- **`blade.workspace`** — `root_dir` and `build_dir` of the active
  workspace. Reading via this fixed handle prevents BUILD files from
  poking at the workspace singleton through back-channels.
- **`blade.host_os` / `blade.host_arch`** — strings describing the machine
  running blade. Useful for conditional `srcs` lists.
- **`blade.build_type`** / **`blade.build_type_is_debug()`** — the active
  profile.
- **Build-phase-only handles**:
  - `blade.current_source_dir()` / `blade.current_target_dir()` — the
    BUILD's own package and its build-dir mirror, populated from the same
    thread-local that drives target keys.
  - `blade.cc_toolchain` — a read-only proxy over the active toolchain
    (`obj_suffix`, `lib_prefix`, `tool('cxx')`, ...). Lets a BUILD file
    parameterize names by toolchain without importing internal classes.
- **Config-phase-only handles**:
  - `blade.getenv(name, default=None)` — read an environment variable
    from `BLADE_ROOT`. The only sanctioned env-access channel; calling it
    from a BUILD file raises a `console.fatal` pointing at the resolved
    toolchain (`blade.cc_toolchain.tool('cc')`) or `blade.config` as the
    BUILD-phase equivalent. Keeping env reads at the config layer puts all
    env dependencies in one auditable file and lets BUILD files stay
    hermetic.

A subset of these attributes are marked `_BUILD_ONLY_ATTRS`: accessing
them from inside `BLADE_ROOT` (config phase) raises a clear error pointing
out that "the toolchain doesn't exist yet — pass a lambda if you need a
deferred value." This is one of the friction-reducing diagnostics that
saves a lot of confused bug reports. `getenv` enforces the symmetric rule
inside the method body (`if not self._config_phase: console.fatal(...)`),
since the BUILD-only attribute path is `__getattr__`-based and methods on
`_BladeModule` don't go through it.

## 3. Sandbox

When `global_config.restricted_dsl` is on (default), each BUILD file's
`__builtins__` is replaced with `restricted.safe_builtins`:

- **Allowed**: type constructors (`int`, `list`, `dict`, `str`, `set`,
  `tuple`, `bool`, ...), the safe end of stdlib helpers (`len`,
  `isinstance`, `hasattr`, `enumerate`, `zip`, `sorted`, `range`, ...).
- **Blocked**: `__import__`, `exec`, `eval`, `compile`, `execfile`,
  `subprocess`, `os.system`, raw file writes. Each blocked name is
  replaced with a wrapper that raises `BuildFileError` at call site,
  carrying the user's BUILD source location.
- **Narrowed**: `open()` is restricted to read mode.

BUILD files are still Python, so users can write loops, list
comprehensions, and helper functions; they just can't reach outside the
sandbox to launch processes, fetch URLs, or import arbitrary modules. The
result is that loading is fast (no surprise subprocess startup, no global
side effects) and the BUILD's behaviour is fully reproducible from its
text plus the workspace tree.

## 4. Argument typing and normalization

Rule args like `srcs`, `hdrs`, `deps`, `incs` are typed `StrOrList` /
`StrOrListOpt` in `blade_types.py`. The type aliases serve documentation
and static analysis; at runtime each rule entry-point routes the value
through `util.var_to_list()` (or `_or_none`), which:

- Accepts a single `str`, a `list`/`tuple`/`set`, or `None`.
- Returns a *fresh* `list[str]` (so subsequent in-place edits on a target's
  attributes don't leak back into a user-supplied list).
- Preserves the `None` ↔ `[]` distinction: `var_to_list(None) -> []`,
  `var_to_list_or_none(None) -> None`. Several attributes (notably
  `hdrs`, `visibility`) use the latter so blade can distinguish "user
  didn't say" from "user explicitly said empty" — for example,
  `hdrs = []` is the way to declare a "header-less library" and exempt it
  from the unused-deps check ([see hdrs check](hdrs_check.md)).

## 5. Implementation details and extension points

- **Adding a new rule** is mechanically `def my_rule(name, ...): ...` plus
  `build_rules.register_function(my_rule)` at module top level, then
  having `load_build_files._load_build_rules()` import the module. The
  rule body typically constructs a `Target` subclass that calls
  `register_target` on itself.
- **`include()` and `load()`** inherit the current BUILD's globals — they
  do not get a fresh sandbox per call, so an `include`'d file behaves as
  if its body were spliced into the caller. `load()` is stricter: it only
  re-exports the explicitly named symbols, so extension scopes stay tidy.
- **Lazy callable config values** — when an item in `cc_config` needs the
  toolchain to resolve, the recommended idiom in `BLADE_ROOT` is to pass a
  `lambda blade: ...` and let `_DeferredConfigValue` invoke it when
  `cc_targets.py` queries the item. Trying to read `blade.cc_toolchain` at
  config-phase raises with the lambda hint, so users don't have to figure
  the pattern out from a stack trace.
- **All diagnostics carry source locations.** Restricted-builtin
  violations, glob() failures, type errors, and registration conflicts go
  through `console.diagnose()`, which prefixes the message with the
  BUILD's path and line. This is why a typo in `srcs=['foo.c']` (missing
  file) reports at the BUILD line of the rule call rather than somewhere
  inside blade.
