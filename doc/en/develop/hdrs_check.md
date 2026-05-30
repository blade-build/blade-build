# How the C/C++ Header Dependency Check (hdrs check) Works

Since Blade 2.0, C/C++ header files are part of dependency management: when a target `#include`s a header, it must declare the library that owns that header in its `deps`, otherwise Blade reports a problem at the end of the build. This document explains **how that check is implemented**; for the user-facing description and fix guidance see [build_rules/cc.md](../build_rules/cc.md#fix-missing-dependencies-errors-caused-by-hdrs).

Source files involved:

| File | Responsibility |
| --- | --- |
| `src/blade/cc_targets.py` | Collect the "header → library" declarations, write per-target check info, generate the check rule |
| `src/blade/build_manager.py` | Write the global declaration to `inclusion_declaration.data` |
| `src/blade/backend.py` | Generate the compile command that emits the inclusion stack (GCC: `cc_wrapper.sh` adds `-H`; MSVC: `cc_wrapper.py` tees `/showIncludes`), plus the `cxxhdrs` and `ccincchk` rules |
| `src/blade/inclusion_check.py` | The actual check logic (invoked as a subprocess at build time) |

---

## 1. Implementation mechanism

The mechanism has three phases: **declaration collection** (while loading BUILD files) → **persisting info** (generation phase) → **emitting inclusion stacks and checking** (build phase).

### 1.1 Collecting "which library owns which header"

While loading BUILD files, each `cc_library` registers the headers it owns into three process-wide global maps (`cc_targets.py`):

- `declare_hdrs()` → `_hdr_targets_map`: **public header** (the `hdrs` attribute) → set of owning libraries.
- `declare_hdr_dir()` → `_hdr_dir_targets_map`: **public include directory** (e.g. `export_incs`, generated dirs) → set of owning libraries.
- `declare_private_hdrs()` → `_private_hdrs_target_map`: **private header** (a `.h` listed in `srcs`) → set of owning targets.

A header may belong to several libraries, so the values are sets.

After all BUILD files (including every transitive dependency) are loaded, `build_manager._write_inclusion_declaration_file()` serializes these three maps together with the `allowed_undeclared_hdrs` config into `<build_dir>/inclusion_declaration.data`, to be read by the check subprocess at build time.

### 1.2 Persisting per-target check info (`.incchk`)

`cc_targets._write_inclusion_check_info()` writes one `<target>.incchk` (pickle) per cc target, holding the local context the check needs:

- `deps`, `expanded_srcs` / `expanded_hdrs` (the expanded source and header lists);
- `declared_hdrs` / `declared_incs`: the public headers/dirs of this target **and of its `deps`** (`_collect_declared_headers()`) — i.e. "the headers that are legal within this target's visibility";
- `declared_genhdrs` / `declared_genincs`: the **generated headers** collected transitively from `deps` (`_transitive_declared_generated_includes()`);
- `severity`, `suppress` (from config).

It also writes a `<target>.incchk.extra` containing `hdrs_deps` / `private_hdrs_deps` / `allowed_undeclared_hdrs` — a **local subset cache** of the global declaration maps, so the check subprocess can query the small file first and avoid loading the large global file every time. It is a separate file so that "information that only exists after the first build" is not mixed into `.incchk` and does not trigger unnecessary rebuilds (see [issue #1034](https://github.com/blade-build/blade-build/issues/1034)).

`.incchk` **is rewritten only when its content changes**, keeping its mtime stable to avoid triggering a needless re-check.

### 1.3 Emitting the "inclusion stack" at compile time (`.incstk` files)

The check needs to know which headers each source/header **actually** includes. The compiler produces this as a side effect of compilation:

- **Source files (GCC/Clang)**: every compile goes through the generated wrapper `cc_wrapper.sh` (see `backend.py`), which appends GCC's `-H` option to the compile command and uses an awk program to separate the "inclusion stack" from ordinary diagnostics, writing it to `<src>.incstk`. The path is passed via the per-object `inclusion_stack` ninja variable, so it is independent of the object-file suffix (`.o` vs `.obj`).
- **Source files (MSVC)**: see the MSVC note below — the same `.incstk` is produced during the normal compile, no separate preprocess.
- **Public headers (all toolchains)**: a header is never compiled into an object, so on **every** toolchain a separate `cxxhdrs` rule preprocesses it (GCC/Clang `-E`, MSVC `/P`) to produce `<hdr>.incstk`. This is independent of the source-file path below — it is the only inclusion stack a header gets.

A `.incstk` file encodes the **inclusion level with the number of leading dots**, for example (GCC format):

```text
. ./app/example/foo.h
.. build64_release/app/example/proto/foo.pb.h
... build64_release/common/rpc/rpc_service.pb.h
. ./common/rpc/rpc_client.h
```

The MSVC format is `Note: including file:  <path>`, using the number of leading spaces for the level. Both are parsed by `inclusion_check._parse_hdr_level_line()`.

#### MSVC: tee `/showIncludes` instead of a separate preprocess

GCC's `-H` writes the inclusion stack to stderr, which the awk wrapper splits off into `.incstk`. MSVC has no `-H`; it emits `/showIncludes` lines (`Note: including file: <path>`) interleaved with diagnostics, and ninja's native `deps = msvc` already parses those same lines to build the dependency graph. To avoid compiling each source file *twice* (once for `.obj` + ninja deps, once to preprocess for the inclusion stack), the MSVC `cc`/`cxx` rules wrap the compile in `cc_wrapper.py`, which **tees** the compiler output:

- it merges the child's stdout and stderr into one pipe (reading only one side risks a pipe-buffer deadlock) and streams every line back to ninja's `deps = msvc` parser unchanged;
- in parallel it writes the `Note: including file:` lines to `<src>.incstk`, so the same single compile feeds both consumers.

Two things are filtered, with **different** treatment for each:

- the **bare basename** the compiler echoes for the file it processes — a cl.exe quirk that cannot be turned off. ninja's `CLParser::FilterInputFilename` already strips this echo **for source files** (it matches `.c/.cc/.cxx/.cpp/.c++`), so the `cc`/`cxx` rules need no help; but it does **not** strip header extensions, so the echoed `foo.h` from the `cxxhdrs` `/P` rule leaks through. We therefore drop any lone filename token ourselves (this also covers nvcc, which echoes its `.cu` source plus intermediate temp names). Such a token is **dropped from both sides** — neither written to `.incstk` nor forwarded to ninja — since it is not a `Note: including file:` line and the deps parser does not need it;
- **absolute paths outside the workspace** (system/SDK headers): these are dropped from `.incstk` only (the checker discards absolute paths anyway, so keeping them would just bloat the file and slow the check), **but still forwarded to ninja** — its `deps = msvc` graph needs the complete include set.

So on MSVC the inclusion stack is a by-product of the normal compile, exactly as `-H` is on GCC — no separate per-source preprocess is needed.

> **Path separators.** The backend writes the declaration data (`declared_hdrs`, the global `public_hdrs` map, …) with the OS separator, i.e. backslashes on Windows, while `/showIncludes` paths are normalized to forward slashes. `inclusion_check.py` reconciles the two by normalizing **all** declaration paths to forward slashes as they are loaded (`_unix_path_set` / `_unix_path_dict` / `_unix_path_pairs`), so the comparisons are separator-agnostic regardless of which platform produced the data.

### 1.4 Triggering the check (the `ccincchk` rule)

`cc_targets._generate_inclusion_check()` generates one `ccincchk` rule per target:

```text
python -m blade.builtin_tools cc_inclusion_check <target>.incchk.result <target>.incchk
```

Its implicit deps are all of the target's `.incstk` files and object files; its output is `<target>.incchk.result` (which contains `OK` when the check passes). That result file is wired as an **order-only dependency** of the link step — so a passing check does not trigger a relink, and a change in check info only re-runs the check rather than relinking.

### 1.5 Running the check (`inclusion_check.py`)

`ccincchk` ultimately calls `inclusion_check.check()`:

1. Load the target's `.incchk` (and `.extra`), and lazily load the global `inclusion_declaration.data` on demand.
2. For each source and header of the target, locate the corresponding `.incstk` and parse it with `_parse_inclusion_stacks()` into:
   - **directly included headers** (level 1, non-absolute path);
   - **generated headers** (paths under `build_dir`): record the **full inclusion stack** from the source to that generated header, and **stop descending** there — deeper inclusions are guaranteed by the generator (e.g. `proto_library`);
   - **absolute paths** (system headers): ignored.
3. Run the two kinds of checks below (sections 2 and 3) over the parsed result.

---

## 2. Check: header not exported / private header used across libraries

This kind targets **directly included** headers and is done in `_check_direct_headers()`. For each directly included header `hdr`:

1. If `hdr` is in this target's `declared_hdrs` → legal, skip.
2. Call `find_libs_by_header(hdr)` to find which **public** library(ies) own it: match the header against the public-header map exactly first; if no match, walk **up the parent directories** matching the public include-directory map.
   - **No public owner found** → check whether it is some target's private header (`find_targets_by_private_hdr()`, i.e. listed in some target's `srcs`):
     - **It is another target's private header** (the owner set does not contain this target) → error:

       ```text
       "X" is a private header file of "//foo:bar"
       ```

       i.e. a **private header used across libraries**. A private header may only be included by its owning library; for another library to use it, the owner should export it by adding it to `hdrs`.
     - **It is not any library's private header** (and not exported by any library) → treated as **undeclared / not exported**, error:

       ```text
       "X" is not declared in any cc target. ...
       ```

       (unless the header is in `allowed_undeclared_hdrs` or in the `suppress` list.) i.e. the header does not appear in any library's `hdrs` or `srcs`.
   - **A public owner is found** → proceed to the "missing direct dependency" check in section 3.

Messages are assembled by `_header_undeclared_message()`, `_hdr_declaration_message()` and `_or_joined_libs()`; the latter shortens libraries in the same directory to `:name` and writes others as `//path:name`.

---

## 3. Check: a header is included but its owning library is not declared in `deps`

This kind is "included a header but did not declare its owning library in `deps`", split into **direct** and **indirect**.

### 3.1 Missing direct dependency (Missing dependency)

Still in `_check_direct_headers()`: when `hdr` has a public owner set `libs`, but the intersection of `libs` with `deps ∪ {self}` is empty → error:

```text
<target>: Missing dependency declaration:
  In file included from "src/foo.cc",
    For "common/rpc/rpc_client.h", which belongs to "//common/rpc:rpc_client"
```

i.e. you directly `#include` a library's public header but did not depend on that library in `deps`. The fix is usually to add the reported library to this target's `deps`.

### 3.2 Missing indirect (generated-header) dependency (Missing indirect dependency)

Done in `_check_generated_headers()`. For each inclusion stack, take the **generated header** `generated_hdr` at its tail:

- if it was already checked as a direct header → skip;
- if it is **transitively declared** (in `declared_genhdrs` / `declared_genincs`, i.e. it comes from some `dep`'s `generated_hdrs`) → legal;
- otherwise → error `Missing indirect dependency declaration`, printing the **full inclusion chain** from the source up to that generated header to help locate the missing link.

**Why is the indirect check restricted to "generated headers"?** If a generated header (a product of `proto_library`, `gen_rule`, etc.) has a missing dependency, it may **not yet be generated** or be a **stale version** when the current target compiles, causing compile errors or — worse — subtle runtime errors. Non-generated headers have their transitive visibility guaranteed naturally by compilation/linking, so they need no enforced declaration and are not checked indirectly.

### Severity and suppression

- `cc_config.hdr_dep_missing_severity`: the severity of a finding (`error` / `warning`). The check fails only when it is `error` and a problem actually exists.
- `cc_config.hdr_dep_missing_suppress`: suppress problems that existed before the upgrade.
- `cc_config.allowed_undeclared_hdrs`: an allow-list of undeclared headers.

See [Configuration](../config.md#cc_config) for details.

---

## Design trade-offs and boundaries

### The completeness boundary: configuration sensitivity

The check is based on the `#include`s the compiler **actually reached** in a single build. `-H` / `/showIncludes` only report the branches that are **active** under the current `#ifdef` / `-D` / target platform and toolchain. So a dependency that is only needed under a *different* configuration (e.g. a header included only under `#if defined(__linux__)` or `#ifdef DEBUG`) is not observed in the current build, and a missing declaration for it goes undetected.

This is not unique to this mechanism: Bazel's sandbox has the **exact same** blind spot — it only constrains the current compile action, and inactive branches are equally invisible. No "single-configuration observation" can be complete across configurations. The practical mitigation is the **CI build matrix**: run the build under several configurations (linux/mac, debug/release, ...) and let each one's check accumulate, approaching global coverage.

### Why `-H` instead of the depfile

The compiler's `-MMD` depfile already lists every header a translation unit uses, but it is **flat** — a set with no inclusion levels, so it cannot distinguish "directly included" from "included indirectly through some header". The two checks here (the "missing direct dependency" and "missing indirect / generated-header dependency" of section 3) depend precisely on that level information, so we must use `-H` / `/showIncludes`, which give an **inclusion tree**; the depfile cannot be reused for this.

### Direct-include detection: `-H` plus a naive source-scan supplement

The set of "directly included headers" drives the missing-dep, private-header, undeclared-header, and unused-dep checks. blade derives it from two sources combined:

- **Authoritative: depth-1 entries from `-H`** in the `.incstk` (`_parse_inclusion_stacks` in `inclusion_check.py`). These are what the compiler actually traversed at depth 1 from this source.
- **Supplement: a regex source-scan** that lists every literal `#include "..."` / `#include <...>` in the source file (`_scan_source_includes`).

The two are combined as:

```text
direct_hdrs = depth-1 ∪ (source_scan ∩ all_paths_in_incstk)
```

The intersection with `_read_all_incstk_paths(...)` — paths the compiler actually traversed at *any* depth — is **the gate**. Anything the compiler did not compile (block-commented `#include`s, `#if 0` blocks, untaken `#ifdef` branches, a mis-quoted system header like `#include "stdio.h"`) naturally drops out at this intersection because it never reaches the `.incstk`. So the scanner is intentionally **naive**: it does not strip comments, does not evaluate `#if 0`, does not track `#ifdef`. Trying to be smarter would be redundant (the intersection already handles it) or even incorrect (e.g. stripping `#if 0 / ... / #endif` blindly would also drop a live `#else` branch).

#### Why the supplement at all

`-H` reports each header at the depth it was *first encountered*; the multiple-include-guard optimization then suppresses any subsequent `#include` of the same header. So a direct `#include "foo.h"` in `bar.cc` is silently elided from depth-1 if some earlier `#include` (e.g. `bar.h`) already pulled `foo.h` in transitively. Without the supplement that case looks like "foo.h is not directly included", producing loud false positives on the unused-deps check and silent false negatives on the other three. See issue #1171.

#### Known limitations

The scan-plus-intersect approach is **not** a real preprocessor. Two corner cases survive:

- **Macro/computed includes** (`#define MY_HDR "x.h"` then `#include MY_HDR`): the regex sees the bare token `MY_HDR` and resolves nothing. `-H` covers these *except* when both macro-form AND guard-suppression occur together — a rare-squared intersection that this design accepts.
- **`#if 0`-d include that is also reached transitively via another live `#include`**: the path appears in `.incstk` via the live transitive chain, so the intersection keeps the scanner's hit. Effect: a "redundant" dep declaration escapes the unused-deps check. Mild, rare.

Additionally, the unused-deps check **exempts system libraries** (deps keyed `#:NAME`, e.g. `#:dl`, `#:pthread`). Their headers do exist (`<dlfcn.h>`, `<pthread.h>`, …) but blade has no system-header → system-lib mapping to consult — and maintaining such a map would be platform- and distro-specific — so a header-based check has nothing to evaluate them against; flagging them would always be a false positive. The same applies to **header-less cc_libraries** (declared `hdrs = []`).

In line with *The completeness boundary* above, the hdrs check is **anchored on what the compiler actually used in this build configuration** — the supplement does not change that principle, it only patches the one place `-H` itself lies (depth-1 elision under guard optimization).

### Relationship to Bazel's sandbox / `layering_check`

Bazel needs **two** mechanisms to cover what this single mechanism does:

- The **sandbox** isolates at the filesystem level: but a `.cc`'s sandbox must contain the **entire transitive closure** of headers (otherwise a legitimate transitive include would fail to find its file). So the sandbox can only stop "including a header that isn't in the closure at all" (fully undeclared); it **cannot tell** "directly included a header of a *transitive* (not direct) dependency" — a strict-deps violation.
- **`layering_check`** supplies the latter: it is built on Clang's module maps + `-fmodules-decluse` ("declared uses") — a module map per library annotates which headers it owns plus `use` edges to its **direct** deps, and the compiler enforces at compile time that "an included header must come from a module the current one declares `use` on". It is compile-time and folded into the normal compile (no `.pcm` actually built), but it **requires toolchain support**: `-fmodules-decluse` is Clang-only, gcc has no equivalent, so Bazel supports the feature only with clang on Unix/macOS.

This mechanism covers **both** with a single "observe + ownership map": `"... is not declared in any cc target"` corresponds to the sandbox's "fully undeclared", and `libs ∩ (deps ∪ self) == ∅` corresponds to `layering_check`'s "a direct include must come from a direct dependency". And because it observes the output of `-H` / `/showIncludes` rather than relying on a Clang-specific enforcement flag, it works on **gcc, clang, and MSVC** alike.

---

## Appendix: related artifact files

| File | Content |
| --- | --- |
| `<build_dir>/inclusion_declaration.data` | Global declaration: public headers/dirs, private headers, `allowed_undeclared_hdrs` |
| `<target>.incchk` | Per-target check info (deps, declared headers/dirs, generated-header declarations, severity, ...) |
| `<target>.incchk.extra` | Local subset cache of the global declaration (avoids loading the large file, avoids triggering rebuilds) |
| `<target>.incchk.result` | Check result; contains `OK` when it passes |
| `<target>.incchk.details` | The direct/generated headers reported by the compiler, used to build the `.extra` cache next build |
| `<src>.incstk` / `<hdr>.incstk` | The inclusion stack of a source/header (produced by `-H` / preprocessing) |
