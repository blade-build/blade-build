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
is either a version string or a dict with `version` and/or `features`:

```python
vcpkg_config(
    packages = {
        'fmt': '10.2.1',                                   # short form
        'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']},
    },
)
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
[`vcpkg_config`](config.md#vcpkg_config) section of the configuration manual for
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
