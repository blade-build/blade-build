# How vcpkg Support Works

Blade consumes [vcpkg](https://github.com/microsoft/vcpkg) libraries as
first-class deps via `vcpkg#<port>:<lib>` references. This document explains
**how it is implemented** ([issue #1236](https://github.com/blade-build/blade-build/issues/1236));
for the user-facing guide see [build_rules/vcpkg.md](../build_rules/vcpkg.md).

Source files involved:

| File | Responsibility |
| --- | --- |
| `src/blade/vcpkg.py` | All vcpkg logic: triplet derivation, `.pc`/CMake parsing, manifest/triplet generation, the `vcpkg#` dep handler, and the managed-install orchestration (`setup`) |
| `src/blade/target.py` | `register_dep_scheme` + `_unify_scheme_dep` — the `<scheme>#<coordinate>` dispatch that routes `vcpkg#...` into the handler |
| `src/blade/cc_targets.py` | `VcpkgLibrary` — the auto-created target that links a resolved port artifact |
| `src/blade/build_manager.py` | `setup_vcpkg()` — calls `vcpkg.setup(self)` between config load and BUILD parsing |
| `src/blade/load_build_files.py` | imports `blade.vcpkg` so the scheme registers |
| `src/blade/config.py` | the `vcpkg_config(...)` schema |

---

## 1. Two phases, cleanly split

vcpkg support is organized so that the **pure, testable logic** is separable from
the side-effecting orchestration. `vcpkg.py`'s module docstring calls these out:

- **Reference resolution** (analysis phase): turn a `vcpkg#port:lib` string into
  concrete install-tree paths, and create a target for it. Pure functions plus
  one handler.
- **Managed install** (`setup`, build phase): generate a manifest + overlay
  triplet and run `vcpkg install`. The only step that touches the network / disk
  heavily.

Most of the module is pure functions over plain inputs (`triplet_for`,
`parse_pkgconfig`, `manifest_json`, `port_required_libs`, …), unit-tested in
isolation; the stateful parts (`_vcpkg_dep_handler`, `setup`) are thin wrappers
that gather inputs from the toolchain/config and call them.

## 2. The `vcpkg#` reference is a dep *scheme*

`vcpkg` extends Blade's `#name` system-library family. A dependency of the form
`<scheme>#<coordinate>` is dispatched by `target._unify_scheme_dep`, and at
import time `vcpkg.py` registers itself:

```python
_blade_target.register_dep_scheme('vcpkg', _vcpkg_dep_handler)
```

The import happens in `load_build_files.py`, so the scheme is live before any
BUILD file is parsed. `#pthread` (no scheme) still means "a system lib resolved
by name"; `vcpkg#fmt:fmt` means "resolve `fmt:fmt` through the vcpkg provider".

## 3. Resolution: `_vcpkg_dep_handler` → `VcpkgLibrary`

When a target depends on `vcpkg#fmt:fmt`, `_vcpkg_dep_handler(referrer, 'fmt:fmt')`:

1. **Governance** — if `vcpkg_config.direct_use_allowed` is set, reject a
   reference from a path outside the allowlist (mirrors the wrapper-library
   discipline large repos use).
2. **Triplet** — `triplet_for_toolchain(toolchain)` derives the triplet from
   Blade's resolved toolchain (`x64-linux`, `arm64-osx`, …); `'auto'` /
   unspecified resolves the static variant (on Windows that means the `-static`
   triplet, since vcpkg defaults to dynamic there).
3. **`resolve_reference(...)`** — pure validation + path math: split
   `port:lib`, enforce the **whitelist** (`port in packages`, else a hard error),
   compute `lib_dir` (the `debug/lib` subtree for an MSVC-ABI debug build, else
   `lib`) and the shared `include_dir`. `lib == 'hdrs'` marks a header-only port.
4. **Target creation** — auto-create one `VcpkgLibrary` (the same pattern as
   `_add_system_library`), keyed by `vcpkg#port:lib` so it is created once and
   reused. For an `'auto'`-linkage port in managed mode it also computes the
   *shared* sibling's `dynamic_lib_dir` in the separate `-shared` install tree.

The `root` / `triplet` are stashed on the target so it can resolve the port's
pkg-config private system libs and transitive `Requires:` siblings **lazily at
generate time** — at analysis time the install tree may not exist yet (the
install runs in between; see §5).

## 4. Parsing what a port actually needs

A single `vcpkg#protobuf:protobuf` reference must pull in the right sibling
archives and system libs. `vcpkg.py` reads that from the install tree:

- `parse_pkgconfig(text)` parses a port's `.pc` file — `Libs` / `Libs.private`
  (the `-l<name>` exports and the private system libs) and `Requires` /
  `Requires.private` (sibling vcpkg modules). `_expand` resolves `${prefix}`-style
  pkg-config variables.
- `port_required_libs(...)` follows those `Requires:` to the sibling archives —
  this is how protobuf (v22+) transparently links the whole `absl_*` +
  `utf8_range` set without the user listing them.
- `port_system_libs(...)` extracts the OS/SDK libs from `Libs.private` and the
  CMake link interface (`_cmake_link_libs`).

These are pure text functions, which is what makes them straightforward to
unit-test against captured `.pc` fixtures.

## 5. Managed install: `setup`

`build_manager.setup_vcpkg()` calls `vcpkg.setup(builder)` once, **after config
load and after analyze, before the install artifacts are needed**. Key behaviors:

- **No-op unless needed** — returns early unless `manage=True` (default) with a
  non-empty `packages`, *and* `_build_uses_vcpkg(builder)` is true. This
  **demand-driven** gate lets a workspace declare `vcpkg_config` unconditionally
  (it is a fixed project property) while a build that references no `vcpkg#...`
  dep pays nothing — and never needs the vcpkg tool.
- **Overlay triplet** — it generates a `blade-<triplet>` overlay
  (`overlay_triplet_cmake`) that **chainloads Blade's resolved compiler**
  (`chainload_cmake`) so the artifacts are ABI-compatible with the rest of the
  build. MSVC is the exception: `cl.exe` uses vcpkg's native toolchain (no
  chainload) so vcpkg sets up the full MSVC environment.
- **Hermetic tree** — manifest (`vcpkg.json`), the chainload cmake, and the
  overlay triplet are written under `<build>/.cache/vcpkg/`; `vcpkg install`
  installs into `installed/<overlay>` there. Only the *artifacts* live under the
  build dir; the vcpkg *tool* is still found via `vcpkg_config.root` /
  `$VCPKG_ROOT` / `PATH` (`_find_vcpkg_tool`).
- **Stamp-skip** — an md5 over `(manifest + chainload + triplet_cmake + overlay)`
  is compared against `.blade-vcpkg-stamp`; an unchanged stamp with an existing
  `installed/<overlay>` skips the install entirely.
- **Second (shared) tree on demand** — `_auto_dynamic_ports(builder, packages)`
  computes which `'auto'` ports a `dynamic_link` binary actually depends on (from
  the analyzed graph — `setup` runs after analyze). Only those are installed a
  second time as shared libraries into a separate `-shared` install root
  (`_install_shared`). An all-static build skips this completely.

## 6. Linkage model

`port_options` / `_effective_linkage` resolve a port's `linkage`
(`'auto'` / `'static'` / `'dynamic'`). The `'auto'` default mirrors
`cc_library`: the static archive always exists, and a shared build is produced
**only on demand** when a `dynamic_link` binary depends on the port — which is
why the shared build lands in a separate `blade-<triplet>-shared` tree (vcpkg
builds one linkage per triplet). `dynamic_ports` / `auto_ports` feed the triplet
and second-install computations above. This is what prevents the
singleton-duplication problem (one shared instance of gflags/protobuf/… across
all dylibs) without per-port configuration.

## 7. Where to look first

- A *resolution* bug (wrong path, missing sibling, whitelist message) →
  `resolve_reference` / `port_required_libs` / `_vcpkg_dep_handler`.
- An *install* bug (wrong triplet, ABI mismatch, re-installs every build) →
  `setup` / `overlay_triplet_cmake` / `chainload_cmake` / the stamp logic.
- A *linkage* bug (static where shared expected, singleton collision) →
  `port_options` / `_effective_linkage` / `_auto_dynamic_ports`.
