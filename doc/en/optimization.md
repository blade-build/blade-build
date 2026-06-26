# C/C++ Optimization (PGO / AutoFDO / LTO)

Advanced, opt-in techniques for squeezing more performance out of **release** C/C++ builds:

- **[Profile-Guided Optimization (PGO)](#profile-guided-optimization-pgo)** — instrument, run a representative workload, rebuild with the collected profile.
- **[Sample-based PGO (AutoFDO)](#sample-based-pgo-autofdo)** — PGO without instrumentation: sample a normal optimized binary (production traffic) and rebuild.
- **[Link-Time Optimization (LTO)](#link-time-optimization-lto)** — cross-module optimization (inlining, devirtualization, dead-code elimination) at link time.

PGO and LTO are independent axes and **compose** (e.g. `--profile-use` + `--lto`); AutoFDO is the no-instrumentation flavor of PGO. The relevant flags are listed in the [command-line reference](command_line.md#subcommand-options); this page is the how-and-why.

## Profile-Guided Optimization (PGO)

Profile-Guided Optimization (PGO), also known as Feedback-Directed Optimization (FDO), is a technique that uses profile data collected from a program's real execution to guide the compiler's optimizations.

PGO is a **global build mode** (not a per-target attribute): you instrument the whole build, run a representative workload, then rebuild using the collected profile. It is wired for **gcc, clang, and native MSVC**; both phases use a dedicated `build_*_pgo` directory so they never clobber your normal `build_*` objects.

```bash
# Phase 1 — instrument, then run a representative workload to collect data
blade build //foo:server --profile-generate=/tmp/pgo
./build_release_pgo/foo/server   # exercise the hot paths

# Phase 2 — rebuild optimized, using the profile
blade build //foo:server --profile-use=/tmp/pgo
```

Toolchain differences blade handles for you:

- **gcc** reads the `.gcda` files directly and adds `-fprofile-correction` (tolerates the count skew of multithreaded programs). Both phases **must** share the build dir — gcc keys its `.gcda` lookup by object path — which the dedicated `build_*_pgo` dir guarantees.
- **clang** needs a *merged* `.profdata`: its instrumented run emits `.profraw`, and `-fprofile-use=` must point at a merged file, not a directory. Point `--profile-use` at the directory of `.profraw` (or an already-merged `.profdata`) and **blade runs `llvm-profdata merge` for you**. clang's `-fprofile-correction` does not exist, so it is not emitted.
- **MSVC** uses whole-program (LTCG) instrumentation: blade compiles with `/GL`, links the instrument phase with `/LTCG /GENPROFILE` and the optimize phase with `/LTCG /USEPROFILE` (and archives with `lib /LTCG`). The instrumented run writes `<binary>!N.pgc` next to the `<binary>.pgd`, and `/USEPROFILE` **auto-merges** them on the optimize link — no `pgomgr` step. The `.pgd` is keyed to the output name, so the shared `build_*_pgo` dir is what lets the optimize phase find the instrument phase's profile. The `path` argument is gcc/clang-specific and is not needed on MSVC (the profile lives next to the binary).

Blade owns the build flags and the clang merge step; producing a *representative* workload (and deciding when a profile is stale) is your job. Profiles are **not** portable across compilers — instrument, run, and optimize all on one toolchain.

> The **instrument** build defines `BLADE_PGO_GENERATE` (a Blade-private macro, not a compiler/industry standard), so source can flush the profile runtime in long-running or forking servers — e.g. `#ifdef BLADE_PGO_GENERATE` → `__llvm_profile_write_file()` (clang) / `__gcov_dump()` (gcc) / `PgoAutoSweep(...)` (MSVC). The **use** build and **AutoFDO** define nothing: those binaries should behave exactly like a normal release.

### Sample-based PGO (AutoFDO)

The instrumentation-based PGO above needs two builds — instrument, then optimize — which is cumbersome, and the instrumented run carries real overhead.

AutoFDO is the **no-instrumentation** flavor of PGO: instead of an instrumented build, you sample a *normal optimized* binary and rebuild with the result. The collection runs at ~1% overhead (vs ~2× for instrumentation), so the profile can come from real production traffic. Works on **gcc/clang** (sample with `perf`) and **native MSVC** (sample with `xperf` — see SPGO below). Uses a dedicated `build_*_autofdo` dir.

```bash
# Phase 1 — build with AutoFDO-friendly debug info, then sample under perf
blade build //foo:server --autofdo-generate
perf record -b -- ./build_release_autofdo/foo/server     # -b = LBR branch records

# Convert perf.data -> a sample profile yourself (it needs the collected binary):
#   clang: llvm-profgen --perfdata=perf.data --binary=build_release_autofdo/foo/server --output=foo.prof
#   gcc:   create_gcov  --binary=build_release_autofdo/foo/server --profile=perf.data --gcov=foo.afdo

# Phase 2 — rebuild using the converted profile
blade build //foo:server --autofdo-use=foo.prof
```

**Typical usage — one build per release (steady state).** Unlike instrumentation PGO (which always needs a separate *slow instrumented* build), AutoFDO's collection binary is a *normal* binary, so once you have a profile you combine both phases into **a single build that is both optimized and collectable**:

```bash
# Each release: optimize with last cycle's profile AND stay sample-able for the next.
blade build //foo:server --autofdo-generate --autofdo-use=foo.prof
# ship it -> sample it in production -> convert -> feeds the *next* release's --autofdo-use
```

`--autofdo-generate` + `--autofdo-use` compose on all three toolchains (gcc/clang add the debug info alongside `-fprofile-sample-use`/`-fauto-profile`; MSVC links `/spgo` alongside `/spdin:` — verified legal on MSVC 14.51, x64 + ARM64). So in steady state every build is simultaneously "optimize with last profile" and "collect for next" — no dedicated extra build. (The very first time, run `--autofdo-generate` alone to bootstrap a profile.) The AutoFDO debug flags are cheap, so you can also bake them into your release config and pass just `--autofdo-use` daily.

- **clang** → `-fprofile-sample-use=<profile>`; the collection build adds `-fdebug-info-for-profiling` + `-funique-internal-linkage-names` (better sample-to-source mapping).
- **gcc** → `-fauto-profile=<profile>`; the collection build relies on debug line tables (the clang flags above are clang-only).
- **Line tables are guaranteed for the collection build.** Sample-PGO maps samples back to source via debug line tables, so `--autofdo-generate` needs them. If `debug_info_level` emits none (e.g. `no`), Blade adds minimal ones for *that build only* — `-gmlt` (clang) / `-g1` (gcc) / `/Z7`+`/DEBUG` (MSVC SPGO) — and prints a one-time notice. It never *downgrades* an existing `-g` (a later `-gmlt` would), so a normal `debug_info_level=mid` build keeps its full debug info.
- **`--autofdo-use` takes an *already-converted* profile**, not a raw `perf.data` — the converter (`llvm-profgen`/`create_gcov`) needs the collected binary, which Blade doesn't have at build time. A raw `perf.data` is detected and rejected with the conversion command.
- **native MSVC** uses its own sample-PGO — **SPGO** ([Sample Profile Guided Optimization](https://devblogs.microsoft.com/cppblog/introducing-sample-profile-guided-optimization-in-msvc/), VS 2022 / 2026 with MSVC 14.51+), which Blade drives from the same `--autofdo-*` flags: `--autofdo-generate` links `/spgo` (collect build), `--autofdo-use=app.spd` links `/LTCG /spdin:app.spd` (both compile `/GL`). You sample with **`xperf`** (IP sampling on any CPU, LBR on Intel Haswell+/AMD Zen 4+/ARM64 ARMv9.2-A+) and convert with **`SPDConvert`** into the `.spd` — those are your step, as with perf. **clang-cl** can't do sample-PGO on Windows (SPGO is cl-only; AutoFDO needs `perf`), so `--autofdo-*` is skipped there with a warning.

**Platform availability (collection vs use).** Sample-PGO *collection* needs hardware sampling: gcc/clang need `perf` + **LBR** (a **bare-metal / PMU-passthrough x86_64 Linux** host — ARM Linux VMs typically expose no PMU/LBR, so `perf record -b` fails there); native MSVC needs `xperf` (IP sampling works on any CPU, including ARM64). **macOS has no sample-PGO collection path at all** (no `perf`, no SPGO; Instruments/`sample`/`dtrace` don't feed `llvm-profgen`) — the `--autofdo-use` flag is still portable, so a Linux-collected profile *can* be applied there, but cross-OS/arch reuse is imperfect and unsupported. Where you can't collect, **use instrumentation PGO** (`--profile-generate`/`--profile-use`) — fully functional everywhere with no special hardware.

> **References:** [GCC AutoFDO tutorial](https://gcc.gnu.org/wiki/AutoFDO/Tutorial) · [MSVC SPGO](https://devblogs.microsoft.com/cppblog/introducing-sample-profile-guided-optimization-in-msvc/)

## Link-Time Optimization (LTO)

LTO performs cross-module optimization (inlining, devirtualization, dead-code elimination) at link time. Whether a project ships with LTO is a **stable decision**, so the primary control is the project intrinsic [`cc_config(lto='thin')`](config.md#cc_config); the `--lto` flags only override it per invocation.

```bash
blade build //foo:server -p release --lto          # ThinLTO for this build
blade build //foo:server -p release --lto=full     # monolithic LTO
blade build //foo:server -p release --lto=no       # off (skip LTO's link cost while iterating)
```

- **thin** (default for `--lto`) maps to clang `-flto=thin` / gcc `-flto=auto`; clang additionally keeps a persistent ThinLTO cache under `<build_dir>/.cache/thinlto/` when the linker supports it (ld64 / lld / gold; GNU `bfd` is detected and the cache omitted). **full** is monolithic `-flto`.
- **Release only:** debug builds never use LTO unless `--lto` is given explicitly. **No separate build dir** (unlike PGO/coverage) — LTO ships and is stable, so it rides `build_release`; toggling triggers a normal full rebuild.
- **Per-target opt-out:** `lto = False` on a `cc_library` keeps it native (linked as an ordinary object alongside the bitcode) — for a TU that miscompiles under LTO, or a library that should stay native.
- **Toolchains: all four** — gcc, clang, native MSVC `cl.exe`, and clang-cl. Native cl maps to `/GL`+`/LTCG` (thin/full both → `/LTCG`, since MSVC LTCG is whole-program; subsumed when a PGO mode is active). **clang-cl** takes the LLVM path instead: `-flto[=thin]` → bitcode, with `lld-link` doing the LTO (+ a `/lldltocache` for thin).

**Toolchain notes / robustness.** clang and clang-cl `thin` is true ThinLTO (incremental, cached). gcc has no ThinLTO, so thin maps to gcc's parallel WHOPR (`-flto=auto`) — a different model with no persistent cache. Native MSVC's `/GL`+`/LTCG` keeps objects COFF (so `cc_check_undefined` reads them with `dumpbin`); clang-cl LTO emits bitcode, so the check routes to `llvm-nm` instead — both keep working. gcc's whole-program LTO is also **less robust on large C++ binaries**: gcc 15.x has been observed to ICE (`internal compiler error: in odr_types_equivalent_p, at ipa-devirt.cc`) when linking heavy protobuf/RPC binaries. An ICE is a compiler bug, not a code error — if you hit one, drop LTO for that binary with `--lto=no` (a per-TU `lto=False` won't help, since the failure is in the whole-program link). In short: clang ThinLTO is the well-trodden path; treat **gcc full-program LTO as experimental**. Runtime gains are also workload- and toolchain-dependent — concentrated on genuinely cross-module hot paths, often negligible elsewhere — so measure on your own hot paths before committing a project to it.

**Self-registration / plugin patterns (a common gotcha).** LTO's whole-program dead-code elimination can drop **static-initializer registrations that are only reached by name at runtime** — factory / plugin / dependency-injection registries, and self-registering objects in general (the `[[gnu::constructor]]` + register-into-a-map idiom). From LTO's whole-program view the registrar is unreferenced, so it — and its `Register(...)` side effect — is stripped; the runtime lookup then fails (`… not found` / a registry `CHECK`) even though the program builds and passes **without** LTO. This is a property of the *code pattern*, not a blade or compiler defect, and it can fail a lot of tests at once if a project's DI mechanism uses it. Note that marking the registrar `__attribute__((used))` is **not always sufficient** (the registry singleton can also be split across translation units under LTO). The reliable fix today: **keep such targets `lto = False`** (or build that binary with `--lto=no`) until the registry itself is made LTO-safe — and always run your test suite under LTO before shipping such a binary.
