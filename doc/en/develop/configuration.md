# How configuration is loaded, layered, and consumed

Blade has a layered configuration system. Settings come from defaults in code,
from one or more config files at well-known locations, and from CLI options
that override specific items at the end. Everything lands in a single
in-memory store consulted by the rest of the codebase.

| File | Role |
| --- | --- |
| `src/blade/config.py` | Schema, load order, registration of `cc_config()` / `cc_library_config()` / ... |
| `src/blade/main.py` | Wiring CLI options on top of the loaded config |
| `src/blade/command_line.py` | CLI options that participate in the override step |

## 1. Layers and precedence

Config files are loaded in a fixed order in `config.load_files()`; each layer
**updates** the in-memory store, so the last writer wins per item. Items not
mentioned by a later layer keep the earlier value (it is not a "use this layer
or nothing" override).

1. **Schema defaults** — `_CONFIG_TEMPLATE` in `config.py` is the source of
   truth for section names, item names, and built-in defaults. It also holds
   `__help__` metadata used by `blade dump`.
2. **`blade.conf`** next to the blade entry point — site-wide defaults for an
   install of blade. Typical use: baseline warnings, default library paths.
3. **`~/.bladerc`** — per-user defaults, persistent across workspaces.
4. **`BLADE_ROOT`** at the workspace root — per-workspace config. Also marks
   where the workspace is; located by walking up from the current directory.
5. **`BLADE_ROOT.local`** — per-checkout / per-developer overrides on top of
   `BLADE_ROOT`. Loaded only when `--load-local-config` is on (default true).
6. **CLI option remap** — at the end of `main.py`, `adjust_config_by_options()`
   translates a small whitelisted set of CLI flags (e.g. `--build-jobs`,
   `--debug-info-level`) back into config calls so they land in the same store
   with the same semantics as if they had been in `BLADE_ROOT`. Other
   options (`--coverage`, `--profile`, `--gprof`, ...) are read directly from
   the parsed `options` object by their consumers.

The accumulated digest of all loaded config text is captured as `config.digest()`
and folded into per-target fingerprints, so any config change invalidates
cached per-target ninja files (see [dependency analysis & ninja generation](dependency_analysis.md)).

## 2. Schema and the `@config_rule` decorator

Every section that a config file can call (`global_config`, `cc_config`,
`cc_library_config`, `proto_library_config`, `cc_toolchain_config`, ...) is a
plain Python function decorated with `@config_rule` in `config.py`. The
decorator registers the function in `_config_globals`, the namespace used to
`exec()` config files. So the set of valid section names is exactly the set
of `@config_rule` functions.

Each rule body calls `_blade_config.update_config(section, append, kwargs)`,
which merges into the section's dict. Three forms of value setting are
supported:

- **Replace** (`cc_config(cppflags=[...])`) — overwrites the item.
- **Append per item** (`cc_config(append_cppflags=[...])`) — `+=` semantics
  for list/set items; an error is raised if both `cppflags` and
  `append_cppflags` appear in the same call.
- **`append=` parameter** — older style, still accepted, marked deprecated in
  diagnostics; the per-item `append_<name>` form is the recommended one.

Multi-instance sections (such as `cc_toolchain_config`, which can be called
multiple times with different names) start as an empty dict in the schema and
are populated key-by-key by their `@config_rule`.

### Type checking

Item types are inferred from the schema defaults — `_assign_item_value` does
an `isinstance(value, type(section[name]))` check against the item's current
value, with two normalizations: a `str` (or anything `var_to_list` accepts)
is coerced into a `list[str]` when the schema item is a list, and into a
`set` when the schema item is a set. A wrong type for a scalar item is a
fatal error that names both the expected and the actual type, so the user
sees `Incorrect type for "cppflags", expect "list", actual "str"` at the
config-file line, not somewhere deep in a target's compile step.

Where the schema's "any value of this type" is not enough, specific
`@config_rule` bodies layer on **enum validation** via
`_check_kwarg_enum_value(kwargs, 'debug_info_level', valid_values)`. This is
how items like `hdr_dep_missing_severity`, `heap_check`,
`duplicated_source_action`, and `cc_toolchain.kind` get their constrained
vocabularies. The check fires before `update_config` runs, so an invalid
value never lands in the in-memory store.

## 3. Runtime access and deferred (callable) values

The rest of blade reads config through two functions:

- `config.get_section(name)` returns a `_ConfigSectionView` — a thin
  dict-like wrapper that lazily resolves each item on access.
- `config.get_item(section, item)` is the one-shot form.

**Why callables are supported.** A few config items need to consult build
context — primarily the toolchain — that does not exist yet when
`BLADE_ROOT` is parsed. The canonical case is the **multi-compiler /
toolchain-selection** story: a workspace may register several
`cc_toolchain_config(...)` entries under different names, then have items
in `cc_config` that should branch on whichever toolchain ends up active
(e.g. emit different cppflags for clang vs msvc, or pull the C++ standard
from the toolchain's defaults). The selection is not finalized at
config-file parse time; it depends on CLI flags and host detection. So
blade lets you write the value as a lambda taking the live `blade` module:

```python
cc_config(
    cppflags = lambda blade: ['-std=c++17']
              if blade.cc_toolchain.cc_vendor != 'msvc'
              else ['/std:c++17'],
)
```

At parse time, `_assign_item_value` sees the callable and (after
`_check_callable_arity` verifies it accepts exactly one parameter) wraps
it in `_DeferredConfigValue`, remembering the **expected return type**
inferred from the schema default. The wrapper is what sits in the section
dict; the function itself is not invoked yet.

At query time, `_resolve_value()` runs the function with the live `blade`
module and rechecks the result's type against the remembered
`expected_type`. A mismatch is reported as a clear "function for X
returned Y, expected Z" error rather than letting a wrong-typed value
flow downstream. There is one escape hatch: during `blade dump --config`
the build manager isn't initialized, so deferred callables are returned
as-is so the dump can still complete.

Targets that resolve a config item repeatedly (e.g.
`PrebuiltCcLibrary._default_libpath` in `cc_targets.py`) cache the resolved
value as a class attribute on first use, avoiding repeated callable
evaluation.

## 4. Implementation details

- **CLI option remap is intentionally narrow.** Only options that are
  semantically the same as a config item go through `adjust_config_by_options()`.
  Mode-changing options (`--coverage`, `--profile`, `--gprof`,
  `--profile-generate/use`) flow as direct attributes on the `options` object;
  consumers read them from there. This keeps "config the build" (knobs)
  separate from "what kind of build are we doing" (commands).
- **Config file sandbox.** Config files are `exec`'d with globals limited to
  `_config_globals` (the `@config_rule` set) plus a deprecated
  `build_target` shim — no full Python builtins. So a config file is not a
  general Python script, only a flat sequence of `<section>_config(...)`
  calls.
- **Platform-conditional rules.** `msvc_config()` is a no-op on non-Windows
  hosts so a cross-platform `BLADE_ROOT` can include it unconditionally
  without affecting Linux/macOS. The schema still carries the MSVC items so
  `blade dump` produces a complete canonical config everywhere.
- **`config.digest()` as entropy.** The MD5 of all loaded config text is part
  of every target's fingerprint, so editing `BLADE_ROOT` invalidates exactly
  the cached per-target ninja files that should be regenerated; nothing else
  needs to track config changes.
- **`blade dump` round-trips the schema.** It walks `_CONFIG_TEMPLATE`,
  resolves every item (including deferred callables), and emits a
  canonical config that could be re-loaded. This is the authoritative
  source of "what items exist and what their current values are".
