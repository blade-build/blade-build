# How C/C++ programs are built

The C/C++ pipeline has four moving parts: a **toolchain abstraction** that
hides the GCC/Clang vs MSVC differences behind a small interface; a
**compile-rule generator** that bakes the per-toolchain templates;
**per-target flag and include-path composition**; and **link rule
construction**. The header dependency check is a separate subsystem
documented in [hdrs check](hdrs_check.md).

| File | Role |
| --- | --- |
| `src/blade/toolchain.py` | `GccToolChain` / `MsvcToolChain` abstraction, vendor detection |
| `src/blade/backend.py` | `cc` / `cxx` / `ar` / `link` / `solink` rule emission |
| `src/blade/cc_targets.py` | Per-target flag/include composition, lib ordering |
| `src/blade/cu_targets.py` | CUDA path; subclasses `CcTarget` |
| `src/blade/build_accelerator.py` | Wrapper interface for ccache/distcc |

## 1. Toolchain abstraction and selection

An abstract `ToolChain` defines the platform-shaped surface every consumer
relies on: file-name shape (`obj_suffix`, `lib_prefix`, `static_lib_suffix`,
`dynamic_lib_suffix`, `exe_suffix`), library naming
(`static_library_name(name)`, `dynamic_library_name(name)`), the tool
fetchers (`get_cc()`, `get_cxx()`, `get_ar()`), and a small vendor query
(`cc_is('clang')`). Two concrete implementations:

- **`GccToolChain`** — used on Linux and macOS. It probes the compiler's
  `--version` output to set `cc_vendor` (gcc, clang, apple-clang, ...) so
  later flag logic can branch on real vendor instead of "gcc-ish vs not".
  This matters because Apple Clang masquerades as `gcc` on macOS, and a
  few GNU-only flags (e.g. `--whole-archive`) would otherwise be emitted
  to a linker that doesn't understand them.
- **`MsvcToolChain`** — Windows only. It locates Visual Studio + Windows
  SDK (from the registry or `vswhere.exe`), maps the requested target arch
  to the right tool directory, and surfaces the system library paths so
  the linker step can emit the right `/LIBPATH:` lines.

`create_toolchain()` picks one in this order: explicit `--cc-toolchain=`
CLI flag, then the `cc_config.toolchain` setting, then any
`cc_toolchain_config()` entry, then platform-based auto-detect. The
selected toolchain becomes the singleton used by every cc target.

Accelerators (`build_accelerator.py`) wrap the compiler-fetching side so
that wiring in ccache or distcc would be a matter of injecting a prefix in
one place; the current implementation passes through the toolchain's
commands unchanged but keeps the seam.

## 2. Compile rules

`backend.py` generates the global ninja rules `cc`, `cxx`, and (when
configured) `secretcc`, plus `cxxhdrs` and `ccincchk` for the header check.

**GCC/Clang form** — the command template is roughly
`cc -o ${out} -MMD -MF ${out}.d -c -fPIC ${cflags} ${cppflags} ${includes}`
wrapped by `cc_wrapper.sh` to also produce the inclusion stack (see
[hdrs check](hdrs_check.md)). `-MMD` is the depfile mechanism ninja
consumes via `deps = gcc` to track header changes, which is independent of
the inclusion-stack-based check.

**MSVC form** — replaces `-MMD` with `/showIncludes` and uses ninja's
`deps = msvc` to parse those lines; the `cc_wrapper.py` shim tees the
output to a `.incstk` so the inclusion check has the same input shape on
Windows. The `cxxhdrs` rule additionally uses `/P` (preprocess to file) +
`/showIncludes` so headers can be checked without being compiled. Paths
that contain spaces are quoted with `/I"path"` since MSVC's parser is
sensitive to that.

`backend.py` also picks up the global intrinsic flags (`-pipe`,
`-fno-omit-frame-pointer`, debug-info level, profile/coverage/PGO flags) so
they don't have to be in every BUILD file. Coverage, profile-generate/use
etc. flow from `command_line.options` here.

## 3. Per-target flag and include-path composition

For each cc target, `cc_targets.py` composes the per-edge variables that
the global rule templates expand:

- **CPP flags**: per-target `-D` defines (from the `defs` attr), plus
  `extra_cppflags`, plus the toolchain's intrinsic cppflags.
- **CXX warnings**: split between C and C++ to honour `cc_config.warnings`
  vs `cc_config.cxx_warnings`.
- **Includes** (`-I.../I...`): the per-target `incs`, plus
  `export_incs` from every transitive dep
  (`_get_incs_list()` walks `expanded_deps`, deduplicates), plus the
  always-present `-I.` (workspace root) and `-Ibuild_dir`.

The `-Ibuild_dir` is what lets a source `#include "proto/foo.pb.h"` resolve
to the generated header at `build64_release/proto/foo.pb.h`. Generated
headers from `gen_rule`/`proto_library` deps are also collected into
`declared_incs` for the inclusion check, but the search-path side is
covered by that single `-Ibuild_dir`.

GCC → MSVC flag mapping (`_map_gcc_flags_to_msvc()` in `toolchain.py`)
translates the common shape (`-std=c++17` → `/std:c++17`,
`-O2` → `/O2`, `-g` → `/Zi`) and silently drops options MSVC doesn't have
(`-W*`, `-pipe`, `-m*`, `-f*`). `-D` and `-I` flow through with their
syntax adjusted. This lets `BLADE_ROOT` keep one `cc_config.cppflags`
list that works everywhere.

## 4. Linking

For each target that produces an executable or shared library, blade
emits one `link` (binary) or `solink` (shared lib) rule call. Three
specifics matter:

- **`@${out}.rsp` response files** for the object/lib list, so long link
  lines don't blow past the OS command-line limit.
- **Static vs dynamic dep ordering** — `_static_dependencies()` and
  `_dynamic_dependencies()` walk `expanded_deps` separately, partitioning
  into system libs (the `#dl`-style ones), user libs, and
  `link_all_symbols` libs. The latter goes into a special spot so the
  linker doesn't drop unreferenced symbols.
- **Platform-specific whole-archive syntax** — selected once in
  `_generate_link_all_symbols_link_flags()`:
  - GNU ld: `-Wl,--whole-archive <libs> -Wl,--no-whole-archive`.
  - Apple ld64 (macOS): `-Wl,-force_load,<lib>` per archive (no
    whole-archive equivalent).
  - MSVC link.exe: `/WHOLEARCHIVE:<lib>` per archive.
  The switch is on `sys.platform` / `os.name`; this is the single place
  cc target code needs to think about cross-platform linker syntax.

Objects land in `<target>.objs/<src.cc>.o` (or `.obj` on MSVC), with
a sibling `<target>.objs/<src.cc>.incstk` for the inclusion check.

## 5. Special target shapes

- **`cc_plugin`** is like `cc_library` but always emits a shared object —
  it's the "release artefact" form, intentionally not pulled in by `deps`
  the way a library is. Prefix/suffix can be customized for projects with
  established plugin naming.
- **`cc_test`** is a `cc_binary` that auto-injects the gtest libraries
  from `cc_test_config.gtest_libs` / `gtest_main_libs`. Heap-check libs
  (gperftools) are added when `heap_check=` is set.
- **CUDA** (`cu_targets.py`) inherits from `CcTarget`. It adds a
  `cudacc` rule (`nvcc -ccbin`), routes its host-compiler flags through
  `-Xcompiler`, and writes the same `.incstk` so the host part of CUDA
  code participates in the hdrs check.

## 6. UX optimizations

- **Header search is `-I.` + `-Ibuild_dir` plus per-target additions.**
  The two-entry default is enough to resolve every workspace-relative
  `#include "pkg/foo.h"` (source) and `#include "pkg/foo.pb.h"`
  (generated). Targets only have to think about `incs`/`export_incs` for
  the rare case of non-workspace-relative headers (e.g. a vendored
  library with its own root).
- **Response files always on** sidesteps the platform-specific
  command-line-length limits without a special case per OS.
- **Per-vendor branching is centralized.** `cc_is(...)` queries and the
  one GCC→MSVC mapping function let target code stay in one shape; the
  toolchain-specific differences live in `toolchain.py` and
  `backend.py` rules, where they can be reviewed in one place.
- **Inclusion stack reuses the compile.** The `-H` (or
  `/showIncludes`) output of the same compile that produces the object
  is also what feeds the header dependency check, so cc targets pay
  essentially nothing extra for the check ([see hdrs check](hdrs_check.md)).
- **Compile parallelism is ninja's default**, but the `heavy_pool`
  (depth 1) referenced by certain rules lets blade serialize compiles
  that don't behave well at high parallelism, without dropping overall
  build parallelism.
