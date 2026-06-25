# How `export_map` (Symbol-Export Control) Works

`export_map` controls which symbols a shared library / executable exports, via a
linker [version script](https://sourceware.org/binutils/docs/ld/VERSION.html).
On GNU ld it is passed straight through; on macOS and Windows — which have no
`--version-script` — Blade *emulates* it. This document explains **how it is
implemented**; for the user-facing description see
[build_rules/cc.md](../build_rules/cc.md#controlling-which-symbols-a-shared-library-exports).

Source files involved:

| File | Responsibility |
| --- | --- |
| `src/blade/cc_targets.py` | `_resolve_linker_input_file` (attr → fullpath, plural-alias handling), `_cc_link` (Linux/macOS dispatch), `_dynamic_cc_library_windows` (DLL `.def` path) |
| `src/blade/builtin_tools.py` | `cc_macos_exports` (ld64 list) and `cc_windef` (`.def` filtering) |

---

## 1. One attribute, three linker realities

The `export_map` attribute is a single version-script file. The mechanism is
**export filtering**, not ABI versioning — hence the name (the deprecated plural
`version_scripts` is an alias). The three backends differ fundamentally:

| Toolchain | Native support | Blade's approach |
| --- | --- | --- |
| GNU ld (Linux) | yes (`--version-script`) | pass through |
| Apple ld64 (macOS) | no | translate to `-exported_symbols_list` |
| MSVC link.exe (Windows) | no | filter the auto-generated `.def` |

Because the macOS/Windows emulation works by **demangled name**, two limits apply
on both: **overloads collapse** (a name is exported with all overloads or none),
and a quoted signature pattern (`"f(int)"`) matches by its name part only (with a
one-time warning). Full ELF version nodes are Linux-only. In practice
`ns::class::method` patterns are sufficient.

## 2. Attribute resolution (`_resolve_linker_input_file`)

`export_map` and the deprecated plural `version_scripts` are normalized into
`export_map_fullpath` (a list of at most one path) by
`_resolve_linker_input_file`, shared with `linker_script`. It:

- warns and falls back if the deprecated plural is used (and ignores the plural
  if both are given);
- warns and keeps only the first file if more than one is given — GNU ld rejects
  two anonymous version nodes, and a single file is the only meaningful count.

Keeping it a one-element list lets it splice straight into the existing
`_cc_link(version_scripts=...)` handling.

## 3. Linux & macOS dispatch (`_cc_link`)

`_cc_link` receives `version_scripts` and branches on the target OS:

```python
if version_scripts:
    if is_darwin:
        # translate to ld64's -exported_symbols_list
        export_map = version_scripts[0]
        exports_list = '%s.exported_symbols_list' % output
        self.generate_build('cc_macos_exports', exports_list,
                            inputs=objs, implicit_deps=[export_map],
                            variables={'export_map': export_map})
        extra_linkflags.append('-Wl,-exported_symbols_list,' + exports_list)
        implicit_deps.append(exports_list)
    else:
        extra_linkflags += ['-Wl,--version-script=%s' % ver for ver in version_scripts]
        implicit_deps += version_scripts
```

- **Linux** — emit `-Wl,--version-script=<file>` and add the script as an
  implicit dep so a script edit relinks.
- **macOS** — a `cc_macos_exports` rule first **converts** the version script
  into an ld64 `-exported_symbols_list` file (see §5), then the link consumes
  it.

(`_cc_link` also handles `linker_script` (`-T`) here; ld64 has no equivalent, so
it is dropped with a warning. MSVC never reaches this branch.)

## 4. Windows DLL path (`_dynamic_cc_library_windows`)

MSVC export control is wired into the **auto-export `.def`** pipeline, not the
link flags. Blade already generates a `.def` from the object files
(`cc_windef`, COMDAT-filtered) to export a DLL's symbols. When `export_map` is
set, that same rule additionally **filters** the `.def` through the version
script:

```python
export_map = self.attr.get('export_map_fullpath')
if export_map:
    def_vars = {'defflags': '--export_map=%s' % export_map[0]}
    def_implicit = [export_map[0]]
self.generate_build('cc_windef', def_file, inputs=objs,
                    implicit_deps=def_implicit, variables=def_vars)
```

The filtered `.def` then drives the DLL link (`/DEF:`), so only the matching
symbols are exported — also useful to stay under the PE 64K export limit.

## 5. The conversion tools (`builtin_tools`)

Both emulations are name-only demangle-and-match, run at build time:

- **`cc_macos_exports`** — enumerates each `.o`'s global symbols via `nm`,
  demangles each via libc++abi's `__cxa_demangle`, matches the demangled name
  against the version script's `global` / `local` patterns, and writes the
  matching (Mach-O underscore-prefixed) mangled names into the
  `-exported_symbols_list` file ld64 reads.
- **`cc_windef`** — the same idea on the `.def`: each symbol's demangled name
  (`UnDecorateSymbolName` / `undname`) is matched against the script; non-matching
  exports are dropped from the `.def`.

The shared trait — *demangling discards overload signatures* — is exactly why
overloads collapse and signature patterns degrade to name-only matching on these
two platforms.
