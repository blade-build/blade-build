# Using vcpkg packages

Blade can consume C/C++ libraries from [vcpkg](https://github.com/microsoft/vcpkg)
— Microsoft's cross-platform package manager (~2500 ports) — as first-class
dependencies, alongside your source targets and system libraries. You reference
a vcpkg library as `vcpkg#<port>:<lib>` in a target's `deps`, declare the
allowed packages once in `BLADE_ROOT`, and Blade takes care of installing and
linking them.

This unifies third-party dependencies across Linux, macOS and Windows and
removes most of the per-package `cmake_build` boilerplate.

## Quick start

1. **Get vcpkg.** Clone and bootstrap it, then either set `VCPKG_ROOT` to that
   directory or put the `vcpkg` executable on your `PATH`:

   ```bash
   git clone https://github.com/microsoft/vcpkg.git ~/vcpkg
   ~/vcpkg/bootstrap-vcpkg.sh        # bootstrap-vcpkg.bat on Windows
   export VCPKG_ROOT=~/vcpkg
   ```

2. **Declare the allowed packages** in `BLADE_ROOT`:

   ```python
   vcpkg_config(
       baseline = '2024-12-15',          # pins the ports tree (recommended)
       packages = {
           'fmt': '10.2.1',
           'openssl': '3.2.1',
       },
   )
   ```

3. **Depend on a library** with `vcpkg#<port>:<lib>`:

   ```python
   cc_binary(
       name = 'app',
       srcs = ['app.cc'],
       deps = [
           'vcpkg#fmt:fmt',
           'vcpkg#openssl:ssl',
       ],
   )
   ```

4. **Build.** By default Blade installs the declared packages and links them:

   ```bash
   blade build //:app
   ```

## Reference syntax: `vcpkg#<port>:<lib>`

A vcpkg dependency extends Blade's `#name` system-library family. The `#`
already means "a library not built from source in this workspace" (`#pthread`,
`#dl`); a scheme in front of it says where the library comes from — here,
`vcpkg`. The part after `#` is the package manager's own coordinate.

| Reference | Meaning |
|---|---|
| `vcpkg#<port>:<lib>` | A specific static library — `lib<lib>.a` (the `lib` prefix is implied). |
| `vcpkg#<port>:hdrs` | A header-only port — only its include directory, no archive. |
| `vcpkg#<port>` | **Rejected** — you must name a library after the port. |

References are always fully explicit: there is no "all libraries of a port"
shortcut, so a multi-library port can never be over-linked by accident.

The library basename can differ from the port name — the vcpkg port
`boost-filesystem` produces `libboost_filesystem.a`, so it is referenced as
`vcpkg#boost-filesystem:boost_filesystem`.

## The package whitelist

`vcpkg_config(packages=...)` is the single source of truth for which ports may
be referenced. Referencing a port that is not listed is a **hard error** — this
keeps every external dependency declared and versioned in one place. Each value
is either a version string or a dict with the keys below:

```python
vcpkg_config(
    packages = {
        'fmt': '10.2.1',                                   # short form
        'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']},
    },
)
```

## Per-port options

The dict form of a package accepts these keys:

| Key | Type | Purpose |
| --- | --- | --- |
| `version` | str | Pin the port version (a vcpkg `overrides` entry). |
| `features` | list[str] | vcpkg features to enable. |
| `linkage` | `'static'` (default) / `'dynamic'` / `'auto'` | How the port is built (see below). |
| `link_all_symbols` | bool | Whole-archive the static lib. |
| `include_prefix` | str / list[str] / dict | Remap the header include path. |
| `cmake_options` | list[str] | Extra CMake configure options for the port. |

### `linkage` — `static` / `dynamic` / `auto`

- **`'static'`** (default) — only the static archive (`.a`) is built.
- **`'dynamic'`** — only the shared library is built; *every* consumer links
  that single instance.
- **`'auto'`** — the static archive is always built, **and** the shared library
  is built *on demand* — only when a `dynamic_link` binary actually depends on
  the port (the same rule as `cc_library`'s `generate_dynamic`). A static-link
  tool then gets a self-contained `.a`, while a `dynamic_link` binary still
  shares one shared library. vcpkg builds one linkage per triplet, so the shared
  build of an `'auto'` port lands in a separate `blade-<triplet>-shared` install
  tree alongside the main static tree.

### `linkage: 'dynamic'` / `'auto'` — singleton libraries

Some libraries keep a process-wide registry behind static initializers — gflags
(the flag registry), glog, protobuf (the descriptor pool), googletest (the test
registry). Linked **statically** into several shared libs and the executable,
each copy gets its own registry and they collide at startup (duplicate flag /
descriptor / test registration). Build such ports **shared** so there is a
single instance. Use `'auto'` when some binaries link them statically (e.g. a
self-contained build-time tool / protoc plugin) while others link dynamically;
use `'dynamic'` to force shared everywhere:

```python
'gflags': {'version': '2.2.2', 'linkage': 'auto'},
'glog':   {'version': '0.7.1', 'linkage': 'auto'},
```

### `link_all_symbols: True` — force static initializers

For a port linked statically *once*, the linker may drop object files whose
symbols are unreferenced — including ones whose static initializers do
registration. `link_all_symbols` whole-archives the lib so they all run. (The
duplicate-copy problem above is the opposite case and needs `linkage:
'dynamic'`, not this.)

### `include_prefix` — remap the header path

A port may ship its headers at `include/` top level (e.g. `snappy.h`) while your
code includes them under a subdir (`"snappy/snappy.h"`). `include_prefix`
exposes the port's include dir under the path(s) you use, with no hand-written
wrapper headers — the port's native layout still resolves too:

```python
'snappy': {'include_prefix': 'snappy'},          # "snappy/h" -> include/h
'zlib':   {'include_prefix': ['zlib', 'thirdparty/zlib']},  # two prefixes
# {prefix: subdir} maps to a header already nested in the port's include:
'glog':   {'linkage': 'dynamic',
           'include_prefix': {'thirdparty/glog': 'glog'}},   # -> include/glog/h
```

### `cmake_options` — extra build options

Pass per-port CMake configure options (emitted as that port's
`VCPKG_CMAKE_CONFIGURE_OPTIONS`). For example vcpkg's snappy disables RTTI
unless asked otherwise:

```python
'snappy': {'include_prefix': 'snappy',
           'cmake_options': ['-DSNAPPY_WITH_RTTI=ON']},
```

## Managed vs. unmanaged installs

`vcpkg_config(manage=...)` selects who runs `vcpkg install`.

### Managed (`manage=True`, the default)

Blade drives vcpkg for you. Before loading BUILD files it generates a manifest
from your whitelist and runs `vcpkg install` into a hermetic tree under the
build directory (`<build>/.cache/vcpkg/`), using an *overlay triplet*
(`blade-<triplet>`) that chainloads Blade's resolved compiler so the artifacts
stay ABI-compatible with the rest of your build. The result is reproducible and
needs no manual steps — just `blade build`. An install is skipped when nothing
relevant changed.

The `vcpkg` **tool** is still located via `vcpkg_config.root`, `$VCPKG_ROOT`, or
`PATH`; only the installed artifacts live under the build directory.

### Unmanaged (`manage=False`)

You run `vcpkg install` yourself, and Blade only resolves paths from the
existing install tree at `<root>/installed/<triplet>/`, where `<root>` is
`vcpkg_config.root` or `$VCPKG_ROOT`:

```bash
vcpkg install fmt openssl          # you install
```
```python
vcpkg_config(manage = False, packages = {'fmt': '10.2.1', 'openssl': '3.2.1'})
```

## Multi-library ports

Ports such as `openssl`, `protobuf` or `icu` produce several archives. Each is
its own target, and you declare the ones you use:

```python
deps = [
    'vcpkg#openssl:ssl',         # libssl.a
    'vcpkg#openssl:crypto',      # libcrypto.a
]
```

A bare `vcpkg#openssl` is rejected, so you never accidentally pull in libraries
you do not use.

## Transitive library dependencies

A port may depend on other vcpkg libraries that it does not itself bundle —
notably `protobuf` (v22+), whose `protobuf.pc` lists dozens of `absl_*` plus
`utf8_range` in pkg-config `Requires:`. Blade follows those `Requires:` and
links the required sibling archives automatically, so a single
`vcpkg#protobuf:protobuf` reference resolves the whole abseil set; you do not
list them yourself. (System/SDK libraries a port needs — `ws2_32`, `dbghelp`,
… — are resolved separately from its `Libs.private` / CMake link interface.)

## Using a vcpkg protoc for `proto_library`

protobuf couples the `protoc` compiler to its runtime version, so generated
`.pb.cc` must be produced by a `protoc` matching the `libprotobuf` you link.
Point `proto_library_config` at the vcpkg-provided protoc (and libprotobuf) so
both come from the same pinned port:

```python
proto_library_config(
    protoc = 'vcpkg#protobuf',                 # protoc from the vcpkg protobuf port
    protobuf_libs = ['vcpkg#protobuf:protobuf'],
)
```

`'vcpkg#<port>'` resolves to the protoc installed in Blade's vcpkg tree. The
resolved protoc binary is tracked as a build input, so bumping the pinned
protobuf version re-runs codegen automatically (no stale `.pb.*`).

## Header-only ports

For a header-only port, use the `:hdrs` sentinel — Blade exposes the include
directory and links no archive:

```python
deps = ['vcpkg#nlohmann-json:hdrs']
```

## Discovering ports and their libraries

### Which ports and versions are available

The available ports and their default versions are fixed by your `baseline`
(the ports tree at that commit). To explore them:

```bash
vcpkg search            # every port and its version in the ports tree
vcpkg search fmt        # ports whose name/description matches "fmt"
```

`vcpkg search` reflects the ports tree at its current checkout. To inspect a
specific `baseline`, check the vcpkg repo out at that commit first
(`git -C $VCPKG_ROOT checkout <baseline>`), or read the version database
directly:

- `$VCPKG_ROOT/versions/baseline.json` — the baseline version of every port.
- `$VCPKG_ROOT/versions/<x->/<port>.json` — every published version of a port.
- `$VCPKG_ROOT/ports/<port>/vcpkg.json` — the port's version, available
  `features`, and its own dependencies.

### Which libraries a port produces

A `vcpkg#<port>:<lib>` reference names the archive `lib<lib>.a`, and the
basename can differ from the port name (`boost-filesystem` →
`libboost_filesystem.a`; `openssl` → `libssl.a` + `libcrypto.a`). Read the
exact names off the installed tree:

```bash
# managed mode (manage=True): under the build dir, with the blade- overlay triplet
ls build64_release/.cache/vcpkg/installed/blade-<triplet>/lib/lib*.a

# unmanaged mode (manage=False): under the vcpkg root
ls $VCPKG_ROOT/installed/<triplet>/lib/lib*.a
```

Each `lib<name>.a` is referenced as `vcpkg#<port>:<name>`. Two more sources:

- `…/installed/<triplet>/lib/pkgconfig/<pkg>.pc` — the `Libs:` line lists the
  `-l<name>` entries the port exports.
- `…/installed/<triplet>/share/<port>/usage` — vcpkg's human-readable hint,
  which usually names the libraries / CMake targets a port provides.

The full list of files a port installed (including every `lib/*.a`) is in
`…/installed/vcpkg/info/<port>_<version>_<triplet>.list`. A header-only port
installs no `lib*.a` — reference it as `vcpkg#<port>:hdrs`.

## Version management and reproducibility

vcpkg's version model is per-workspace (one version and one feature set per
package), which `vcpkg_config` maps onto directly:

| `vcpkg_config` field | vcpkg manifest field |
|---|---|
| `baseline` | `builtin-baseline` |
| `packages[pkg]` version | `overrides[].version` |
| `packages[pkg]['features']` | `dependencies[].features` |
| `registries` | `registries[]` (private registries) |

For reproducible builds, pin `baseline` to a ports-tree commit (a date or git
SHA); add every declared package to a version for the strongest guarantee.
Blade installs the whole whitelist together, so the set stays consistent.

## Triplets

The triplet is derived automatically from Blade's toolchain
(`x64-linux`, `arm64-osx`, `x64-windows-static`, …). In managed mode Blade uses
a `blade-<triplet>` overlay that chainloads your compiler. Override the base
triplet with `vcpkg_config(triplet='...')` when you need a specific one.

## Wrapping for large repositories

If your repository already routes third-party code through a `//third_party/`
layer, hide the `vcpkg#` references behind ordinary `cc_library` wrappers so
business code never sees them:

```python
# //third_party/openssl/BUILD
cc_library(name='ssl',    deps=['vcpkg#openssl:ssl'],    visibility='PUBLIC')
cc_library(name='crypto', deps=['vcpkg#openssl:crypto'], visibility='PUBLIC')

# //services/payment/BUILD
cc_library(name='payment', srcs=['payment.cc'], deps=['//third_party/openssl:ssl'])
```

## Configuration reference

All settings live in `vcpkg_config(...)` in `BLADE_ROOT`. See the
[`vcpkg_config`](../config.md#vcpkg_config) section of the configuration manual for
the full list of fields (`manage`, `baseline`, `packages`, `registries`, `root`,
`triplet`, `install_dir`, `binary_cache`, `direct_use_allowed`).

## Troubleshooting

- **`vcpkg port "X" is not in the vcpkg_config.packages whitelist`** — add the
  port to `vcpkg_config(packages=...)`.
- **`the vcpkg tool was not found`** (managed mode) — set `vcpkg_config(root=...)`,
  `$VCPKG_ROOT`, or put `vcpkg` on `PATH`.
- **`static library not found at ...`** — the archive for that library is not in
  the install tree. Check the library basename (it may differ from the port
  name), and in unmanaged mode make sure you ran `vcpkg install` for the same
  triplet.
- **`a port must name a library`** — a reference is missing its `:lib`; use
  `vcpkg#<port>:<lib>` (or `vcpkg#<port>:hdrs`).
