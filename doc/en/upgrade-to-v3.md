# Upgrading to V3

## Overview

V3 is a comprehensive modernization upgrade with the following goals:

- **Python 3.10+ only**, removing all Python 2 and older Python 3 compatibility code
- **Full type annotations**, all build target modules now have PEP 604 type hints with pyright static checking
- **Code cleanup**, removing dead code and invalid tests, fixing known bugs
- **Experimental macOS support**, fixing multiple macOS compilation compatibility issues
- **Modernized build-dir naming**, the default drops the legacy `64` (`build64_release` → `build_release`) and gains `${os}`/`${arch}` template variables for multi-platform builds

Upgrading to V3 gives you:

- Better type safety, reducing parameter errors when writing BUILD files
- Comprehensive unit tests and cross-repo E2E smoke test coverage
- Cleaner code structure, easier to extend and develop
- Blade can run on macOS (experimental)
- Better documentation coverage (new Go build docs, `$(location)` syntax docs)

## Upgrade FAQ

### Python version

V3 **only supports Python 3.10 and above** (tested on 3.10 - 3.14 via CI). Python 2.7 and older Python 3 versions supported by V2 are no longer supported.

If your system's default Python is below 3.10, set the `BLADE_PYTHON_INTERPRETER` environment variable to point to Python 3.10+:

```bash
export BLADE_PYTHON_INTERPRETER=/usr/bin/python3.12
```

### BUILD file syntax

V3 is **fully compatible** with V2 BUILD file syntax. All build rules (`cc_library`, `cc_binary`, `java_library`, `proto_library`, etc.) keep the same parameters and behavior.

The only difference: `fbthrift_library` has been removed (never implemented for the ninja backend). If your BUILD files use `fbthrift_library`, migrate to `thrift_library`.

### Removed features

The following features have been removed in V3:

- **`fbthrift_library`** — never implemented for the ninja backend; `generate()` unconditionally errored. Use `thrift_library` instead.
- **`swig_library`** — not yet implemented for the ninja backend (rule registration kept, but errors at build time).
- **`example/` directory** — examples moved to the standalone [blade-test](https://github.com/blade-build/blade-test) repository.
- **`fbthrift_library_config` config function** — removed (but kept as a no-op stub so existing `BLADE_ROOT` files don't break).

### macOS support

V3 fixes the following macOS compatibility issues:

- `-static-libgcc` / `-static-libstdc++` are no longer used on macOS (clang doesn't support these GCC-specific flags)
- `--whole-archive` / `--no-whole-archive` replaced with `-force_load` on macOS

macOS support is currently **experimental**. Validate in CI before production use.

### Global config changes

The `fbthrift_library_config` call has been removed from `blade.conf`. If your `BLADE_ROOT` or `blade.conf` references `fbthrift_library_config`, it will not error (a no-op stub is kept), but removing the reference is recommended.

### Extensions and utilities

`load()` and `glob()` extension mechanisms remain unchanged. The following path safety validations have been added:

- `gen_rule.outs` disallows `..` (parent directory traversal)
- `cc_library.incs` and `cc_library.export_incs` disallow `..`
- `glob()` include patterns disallow `..`

### Build directory name

The default build directory was renamed from `build64_<profile>` to `build_<profile>` — e.g. `build64_release` → `build_release`. The legacy `64` was a 32-/64-bit multilib leftover that couldn't distinguish `arm64` from `x86_64`; the platform now comes from the selected toolchain, and `global_config.build_path_template` gained `${os}`/`${arch}` variables for projects that build for several platforms:

```python
global_config(build_path_template = 'build_${os}_${arch}_${profile}')
# build_linux_x86_64_release, build_darwin_arm64_release, ...
```

This is the only change with a one-time cost:

- Your old `build64_*` trees go cold (one rebuild into the new `build_*` dir). Blade prints a one-time notice when it finds a stale `build64_*` beside the new dir; delete the old tree at your convenience.
- Update `.gitignore`, CI cache keys, and any scripts that reference `build64_*` to `build_*` (or a glob covering both).
- **To keep the old name**, pin it in `BLADE_ROOT` — it reproduces the v2 layout exactly:

```python
global_config(build_path_template = 'build${bits}_${profile}')   # -> build64_release
```

The legacy `-m32`/`-m64` flag is also deprecated (it was the x86 multilib selector); select a toolchain whose arch is 32-/64-bit instead — the toolchain then determines `${arch}`/`${bits}`.

## V2 → V3 Upgrade Steps

1. **Upgrade Python**: ensure Python 3.10+ is available and set as blade's default interpreter.
2. **Update blade**: pull the `master` branch or checkout the latest v3 tag (e.g. `v3.0.0-beta`).
3. **Check BUILD files**: replace any `fbthrift_library` references with `thrift_library`.
4. **Check BLADE_ROOT**: remove `fbthrift_library_config` calls (optional but recommended).
5. **Verify compiler**: macOS users, confirm clang is available; Linux users, confirm GCC or clang.
6. **Build dir rename**: the default build dir is now `build_<profile>` (was `build64_<profile>`); update `.gitignore` / CI cache keys / scripts, or pin `build_path_template = 'build${bits}_${profile}'` to keep the old name.
7. **Run build**: `blade build ...` to verify the project builds correctly.

If you encounter problems, please file an [issue](https://github.com/blade-build/blade-build/issues).
