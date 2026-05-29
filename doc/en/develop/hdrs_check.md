# How the C/C++ Header Dependency Check (hdrs check) Works

Since Blade 2.0, C/C++ header files are part of dependency management: when a target `#include`s a header, it must declare the library that owns that header in its `deps`, otherwise Blade reports a problem at the end of the build. This document explains **how that check is implemented**; for the user-facing description and fix guidance see [build_rules/cc.md](../build_rules/cc.md#fix-missing-dependencies-errors-caused-by-hdrs).

Source files involved:

| File | Responsibility |
| --- | --- |
| `src/blade/cc_targets.py` | Collect the "header → library" declarations, write per-target check info, generate the check rule |
| `src/blade/build_manager.py` | Write the global declaration to `inclusion_declaration.data` |
| `src/blade/backend.py` | Generate the compile command that emits the inclusion stack (`cc_wrapper.sh` adds `-H`), plus the `cxxhdrs` and `ccincchk` rules |
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

- **Source files**: every compile goes through the generated wrapper `cc_wrapper.sh` (see `backend.py`), which appends GCC's `-H` option to the compile command and uses an awk program to separate the "inclusion stack" from ordinary diagnostics, writing it to `<src>.incstk`. The path is passed via the per-object `inclusion_stack` ninja variable, so it is independent of the object-file suffix (`.o` vs `.obj`).
- **Public headers**: a header is not compiled normally, so a separate `cxxhdrs` rule preprocesses it (`-E`) to produce `<hdr>.incstk`.
- **MSVC**: it does not emit an inclusion stack during compilation (it uses ninja's native `deps = msvc` to parse `/showIncludes`), so an extra `cxxhdrs` preprocess step is added for source files too.

A `.incstk` file encodes the **inclusion level with the number of leading dots**, for example (GCC format):

```text
. ./app/example/foo.h
.. build64_release/app/example/proto/foo.pb.h
... build64_release/common/rpc/rpc_service.pb.h
. ./common/rpc/rpc_client.h
```

The MSVC format is `Note: including file:  <path>`, using the number of leading spaces for the level. Both are parsed by `inclusion_check._parse_hdr_level_line()`.

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
