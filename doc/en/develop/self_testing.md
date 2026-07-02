# How blade-build itself is tested

Blade-build's own test pyramid has three layers — unit, integration /
E2E, and smoke — each with a different scope, runner, and CI shape.
Coverage is captured during the integration layer's subprocess runs and
merged across layers and Python versions before being uploaded.

| Layer | Where | Driver | What it exercises |
| --- | --- | --- | --- |
| **UT** | `src/tests/unit/` | `unittest`/`pytest`, no subprocess | Pure-Python logic of one module in isolation |
| **Integration / E2E** | `src/test/` (`blade_test.py` harness) | Spawns real `blade` against `testdata/` | The whole pipeline end-to-end on a small workspace |
| **Smoke** | `.github/workflows/*` + sibling `blade-test` repo | Two flavours (see below) | Sanity check and cross-repo acceptance |

Plus type-check (`pyright`) and link-check workflows that run alongside.

## 1. Unit tests

Files under `src/tests/unit/` are plain Python test modules — usually
`unittest.TestCase` subclasses, sometimes run via `pytest`. They are
hermetic: no subprocess, no testdata workspace, no compiler. A unit
test imports the blade module under test, builds a minimal in-memory
state, and asserts on the result. Examples (representative shape only,
the docs don't track specific cases): the toolchain abstraction's
platform-specific naming logic, `var_to_list` boundary helpers, the
header inclusion-check `Checker` in isolation.

Locally: `python3 -m unittest discover -s src/tests/unit -p '*_test.py'`
(`src/tests/unit/runall.sh` does this with `PYTHONPATH` already set
up). CI runs `pytest src/tests/unit`. On Linux the Python version
matrix is the full supported range (currently 3.10–3.14); macOS and
Windows pick a relevant subset of unit modules that are
platform-agnostic enough to exercise on those hosts too.

## 2. Integration / E2E tests

The harness is `src/test/blade_test.py` with `TargetTest` as the base
class. A test:

- Calls `doSetUp('subdir', target='...')` to chdir into the shared
  `src/test/testdata/` workspace and reset its `build_release/`
  artifacts.
- Calls `runBlade('build')` (or `'test'`) which spawns a real
  `../../../blade build <targets> --generate-dynamic --verbose` and
  captures stdout/stderr to files.
- Asserts on the captured output via `inBuildOutput(kwlist)` /
  `findBuildOutput(kwlist)` helpers.

`testdata/` is a **single shared workspace** with subdirectories per
domain (cc, java, lex_yacc, hdr_dep_check, guard_suppression,
header_only_incstk, ...). Each integration test cleans only its target's
artifacts, so tests run **serially** — duplicating the testdata to
parallelize hasn't been needed at the current suite size.

Local runner is `src/test/run.sh <file>` (and `runall.sh` for the
whole suite). On CI, integration is one of the longer-running jobs in
`python-package.yml`. The blade subprocess uses the in-tree code
(invoked as `../../../blade`), so a change in `src/blade/...` is
exercised the same run.

The suite `runall.sh` runs is built from the explicit `TEST_CASES` list
in `blade_main_test.py`, so a new integration test class must be added
there to run in CI. `tests/unit/integration_suite_coverage_test.py`
guards this: it fails if any `src/test/*_test.py` class that defines a
`test*` method is missing from `TEST_CASES`, so a test can no longer be
silently dropped from CI.

## 3. Smoke tests

Two distinct things both go by "smoke":

- **In-process smoke** in `macos-ci.yml` / `windows-ci.yml`: imports
  blade modules, calls `create_toolchain()`, checks the per-platform
  naming output is the expected shape (`libfoo.a` vs `foo.lib`,
  clang on macOS, msvc on Windows). No subprocess, no real build —
  just a quick "the package even imports correctly on this OS."
- **Cross-repo E2E smoke** in `python-package.yml` / `macos-ci.yml` /
  `windows-ci.yml`: checks out the sibling `blade-test` repo and runs
  `./blade.sh test //suites/...` against its fixtures (cc_basic,
  java_basic, lex_yacc_basic, py_basic, resource_basic, ...). This is
  what catches integration breakages that only show up against a real
  toolchain — and is gated behind the UT + integration jobs so it
  only runs when the cheaper layers are happy.

## 4. Coverage

Capture happens at the integration layer, in `src/test/run.sh`:

```sh
BLADE_PYTHON_INTERPRETER="$PYTHON -m coverage run \
    --source=$ROOT/src/blade --rcfile=$ROOT/.coveragerc"
```

So every `blade` subprocess the integration tests spawn runs under
`coverage`. `.coveragerc` sets `parallel = true`, which writes
`.coverage.<pid>` files per process — essential because blade spawns
its own subprocesses (compilers, codegen tools) during the build, and a
single `.coverage` file would be racy.

After tests finish, `run.sh` calls `coverage combine` to merge the
per-process files into one `.coverage`, then `coverage report` for the
terminal summary.

In CI, one Python version (typically the one chosen for the integration
matrix entry) goes one step further: after integration completes, the
unit tests are re-run under `coverage run -m pytest src/tests/unit`,
and `coverage combine --append` merges them on top of the integration
baseline. The combined file is then uploaded to Coveralls via
`coveralls --service=github`. The upload step is `continue-on-error`
because Coveralls outages are not allowed to fail the build.

## 5. CI orchestration

`.github/workflows/`:

- `python-package.yml` (Ubuntu) — unit + integration + e2e-smoke +
  coverage merge + Coveralls upload. Matrix across the supported
  Python versions; coverage merge runs on one of them to avoid
  duplicate uploads.
- `macos-ci.yml` — platform-relevant unit subset + in-process smoke +
  e2e smoke. Python matrix subset.
- `windows-ci.yml` — the equivalent on Windows.
- Auxiliary: `pyright` (type check), `codeql` (static analysis),
  `check-md-links` (documentation link check). These run independently
  of the test pyramid.

The cross-OS jobs deliberately exercise the **platform-shaped** parts
of blade (toolchain detection, naming, MSVC-specific paths) rather than
re-running the entire Linux suite. The flip side is that any logic
that's not exercised on macOS/Windows in the smoke matrix will only
catch breakage when a downstream user reports it — a real consideration
when changing toolchain code.

## 6. Implementation details and UX optimizations

- **Integration runs serially against one testdata workspace.** This
  is the single biggest constraint and the main reason the suite
  stays small. The trade is: clean cleanup logic + simple harness,
  versus duplicating testdata per test. The current size makes the
  former clearly win.
- **`BLADE_PYTHON_INTERPRETER`** is the seam coverage uses, but it
  also lets developers debug a specific Python version without
  modifying scripts. Setting it to `python3.13 -m coverage run ...`
  reruns a single failing test under coverage with the same flags as
  CI.
- **`parallel = true` in `.coveragerc` is mandatory.** Without it, a
  blade subprocess that itself spawns Python subprocesses (the
  inclusion check, builtin tools, ...) would have concurrent writers
  on `.coverage` and produce a corrupt file.
- **Coverage merge across layers.** Doing the unit-test pass under
  `coverage run` + `coverage combine --append` after the integration
  pass means the uploaded number reflects both layers; otherwise
  unit-only coverage of helpers that integration also exercises
  would double-count or be reported separately.
- **`continue-on-error` on Coveralls upload.** Treating external
  reporting as best-effort is what keeps the build status honest:
  CI doesn't go red because a third-party API is down.
- **Cross-OS smoke is intentionally cheap.** A full integration
  suite on macOS/Windows would be slow and brittle (toolchain
  versions differ, library paths differ); the in-process smoke +
  E2E against `blade-test` gives high signal at low cost.
- **Hermetic UT vs heavy integration.** This split is what makes the
  inner loop fast: a fix-and-test cycle on a unit test is sub-second;
  the integration suite is reserved for "did the wiring change."
