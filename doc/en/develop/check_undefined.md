# How the Static Undefined-Symbol Check (`check_undefined`) Works

A `cc_library` is an archive (`.a`/`.lib`), which a linker happily builds even if
it references symbols no dependency provides — the error only surfaces much later
when some binary links it. `check_undefined` closes that gap: it verifies, per
library, that every undefined external is satisfied by the library's declared
`deps`, **without** doing a shared link. This document explains **how it is
implemented**; for the user-facing description see
[build_rules/cc.md](../build_rules/cc.md#static-undefined-symbol-check).

It is [experimental](https://github.com/blade-build/blade-build/issues/1225);
findings default to `warning` severity.

Source files involved:

| File | Responsibility |
| --- | --- |
| `src/blade/cc_targets.py` | `_emit_archive_syms` (one `nm`/`dumpbin` per archive) and `_generate_check_undefined` (collect each target's spec) |
| `src/blade/build_manager.py` | `register_cc_check_undefined` / `cc_check_undefined_specs` — accumulate specs; the system-symbol caches |
| `src/blade/backend.py` | `_emit_cc_check_undefined_batch` — write the manifest + emit the single `ccchkund_batch` ninja edge |
| `src/blade/builtin_tools.py` | `generate_cc_check_undefined[_batch]` — the actual symbol set-difference, run as a subprocess at build time |
| `src/blade/toolchain.py` | `STATIC_LIB_SYMS_LABEL`, the `ccsyms` rule (nm vs dumpbin), default-linked-libs baseline |

---

## 1. The idea: a symbol set-difference, computed once

The check is, at heart: **`undefined(lib) − defined(lib ∪ deps ∪ system) ⊆ allowlist`**.
The implementation's whole effort is making that cheap and reliable across a big
graph:

1. Run the symbol reader (`nm`, or `dumpbin` on MSVC) **once per archive**, not
   once per consumer.
2. Cache each archive's symbols in a `<archive>.syms` text file (undefined `#U`
   and intra-archive defined `#D` sections).
3. Pre-generate `.syms`-format caches for system libraries.
4. Do the set-difference in a **single batched subprocess** for the whole
   project, rather than one Python process per library.

## 2. `.syms` per archive (`_emit_archive_syms`)

When a `cc_library` produces its archive, `_emit_archive_syms` emits a `ccsyms`
ninja rule that runs `nm` once and writes `<archive>.syms`, recorded under the
toolchain's `STATIC_LIB_SYMS_LABEL`. It is **idempotent** — re-registering the
same label on a target is a no-op, so an archive is never nm'd twice. On MSVC the
archive is a COFF `.lib` read with `dumpbin`; the `.syms` format is identical, so
everything downstream is platform-agnostic.

This is the key scaling move: it "collapses what used to be O(targets × deps)
`nm` invocations down to one `nm` per archive total", because a dependent reads
its dep's cached `.syms` instead of re-nm-ing the dep's archive.

## 3. Per-target spec (`_generate_check_undefined`)

For each `cc_library` (unless opted out — see §6), this collects the inputs the
check needs and registers a *spec* on the BuildManager:

- `target_syms` — the library's own `<archive>.syms` (used for both its `#U`
  undefined set and its `#D` defined set).
- `dep_syms` — each transitive `cc_library` dep's `.syms` (the `#D` set only).
- `sys_caches` — for each system-lib dep (`path == '#'`), its pre-generated
  symbol cache (resolved via `get_system_symbol_cache` or carried on an
  absolute-path lib), **plus** the toolchain's default-linked-libs baseline
  (`get_default_linked_system_caches` — msvcrt/ucrt/… on MSVC, libc/libm/…
  elsewhere). De-duplicated, since an alias can appear in both.
- `allow_file` — the per-target + global `allow_undefined` regexes written to a
  `<archive>.a.allow` sidecar so they survive shell quoting and ninja variable
  substitution intact.

The system-cache step is what lets the check **enforce system-lib discipline**:
`pow()` resolves only if the consumer declares `'#m'`, because libm's symbols are
in `sys_caches` only when `#m` is a dep.

## 4. One batched ninja edge (`backend._emit_cc_check_undefined_batch`)

Rather than a per-target `ccchkund` rule (which paid one Python-interpreter
startup *per library* on every build), all specs are accumulated and the backend
emits a **single** `ccchkund_batch` edge after every target has generated:

- Specs are sorted by `target_label` and serialized to
  `.cache/cc_check_undefined.manifest.json` (write-if-changed, so the manifest is
  byte-stable and doesn't spuriously re-trigger).
- The edge's explicit inputs are the manifest + every distinct `.syms` cache (so
  ninja re-runs the batch precisely when any symbol set changes); the `.allow`
  files are implicit deps.
- The output is a stamp file, and **no `default` is declared** — ninja
  auto-builds leaf outputs, so the stamp is reached without overriding ninja's
  leaf discovery (which would break `blade build //some:target`).
- **Cached regen** — if every cc_library's sub-ninja was reused this run, no spec
  is registered, but the previous manifest on disk is re-emitted so the main
  `build.ninja` regen stays idempotent. With genuinely nothing to check (MSVC
  with everything opted out, or no manifest), it emits nothing.

Because the stamp has **no consumers** (no build node depends on the result), the
batch doesn't serialize against the rest of the build — it runs in parallel and
only *reports*.

## 5. The check itself (`builtin_tools`)

`generate_cc_check_undefined_batch` runs at build time as the `ccchkund_batch`
subprocess. For each spec it loads the `.syms` files, computes
`undefined − (own_defined ∪ dep_defined ∪ system_defined)`, drops anything
matching an `allow_undefined` regex, and reports the remainder at the configured
`severity`. The non-batched `generate_cc_check_undefined` is the same logic for a
single target (kept for clarity / direct invocation).

## 6. Opt-outs and where it doesn't run

`_generate_check_undefined` returns early (no spec) when:

- `check_undefined = False` on the target (CLI `--cc-check-undefined` /
  `--no-cc-check-undefined` and `cc_library_config.check_undefined` set the
  default; per-target `False` always wins — see the tri-state resolution in
  `CcTarget.__init__`).
- `allow_undefined = True` — the legacy "unresolved by design, the consumer
  provides them" signal, which also disables `-Wl,--no-undefined` at link time;
  the static check would contradict it. (A *list* `allow_undefined` is an
  allowlist and continues through the check as regexes.)

It also runs for `generate_dynamic` libraries: the dynamic link's
`-Wl,--no-undefined` is the final word, but the static check catches the same
miss per-library *before* any link runs, with faster feedback (#1225). On MSVC it
works via `dumpbin`, with the CRT covered by the default-linked-libs baseline so
`/DEFAULTLIB` directives don't false-positive.
