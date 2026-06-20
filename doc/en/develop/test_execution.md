# How `blade test` runs user tests

Test execution sits on top of the regular build: once the binaries are
ready, blade decides which ones are worth running this time, prepares a
per-test sandbox, schedules them in parallel (with one carve-out for
exclusive tests), captures their results, and updates a persistent
history so the next run can skip the unchanged ones.

| File | Role |
| --- | --- |
| `src/blade/test_runner.py` | Discovery, history-based dedup, result aggregation |
| `src/blade/test_scheduler.py` | Parallel job dispatch, worker threads, timeout |
| `src/blade/binary_runner.py` | Per-test runfiles dir, env vars, testdata staging |
| `src/blade/config.py` | `cc_test_config`, `global_config.test_timeout`, `test_related_envs` |

## 1. Pipeline overview

1. `TestRunner.run()` collects every `*_test` target (`cc_test`,
   `java_test`, `py_test`, `scala_test`, `sh_test`, ...) and asks
   `_run_reason()` for each whether it needs to run this time.
2. For tests that do, `BinaryRunner._prepare_env()` builds a per-test
   `<target>.runfiles` directory, symlinks shared libs in, copies
   testdata, and assembles the env dict.
3. `TestScheduler.schedule_jobs()` dispatches the jobs across worker
   threads. Tests marked `exclusive=True` get a separate single-worker
   pass after the parallel batch.
4. After all jobs complete, the runner merges results into the test
   history file, writes the JSON summary, and prints the
   passed/failed/unchanged/repaired counts.

## 2. Per-test environment

Each test runs with `cwd=<target>.runfiles`. The directory is rebuilt
from scratch every run; into it go:

- **A symlink of the build dir** (`runfiles/<build_dir_basename> ->
  <abs build dir>`). Blade-built shared libs carry their relative
  build path as their identity (no soname / no `@rpath`), so this
  symlink is what lets `build_release/lib/libfoo.so` resolve at
  runtime from the test's cwd. This was the fix for issue #1167 and
  also makes macOS dyld and Linux ld.so behave the same way without an
  OS branch.
- **Per-soname symlinks** for prebuilt libraries that do carry a
  soname (`libcrypto.so.1.0.0`, ...). Found at runtime via the
  `LD_LIBRARY_PATH` blade prepends to point at the runfiles dir.
- **Staged testdata** copied from the target's `testdata` attr (and from
  any sibling `<target>.testdata` file). Items can be plain paths or
  `(src, dst)` tuples; `//`-prefixed paths are workspace-relative.

The env passed to the test is a copy of `os.environ` plus:

- `LD_LIBRARY_PATH` (runfiles + configured `run_lib_paths`).
- `PATH` extended with `java_home/bin` if `java_config.java_home` is set.
- `GTEST_COLOR`, `GTEST_OUTPUT=xml`, `HEAPCHECK` (per-target),
  `PPROF_PATH`, `BLADE_COVERAGE` when applicable.

Windows skips the soname-symlink path (PE loading does not look there
anyway), so this whole sandbox is POSIX-shaped.

## 3. Parallel scheduling

`TestScheduler` runs two passes:

- **Normal pass**: up to `global_config.test_jobs` worker threads pull
  jobs from a shared queue. Each worker runs one `subprocess.Popen`,
  captures stdout/stderr, applies the per-test timeout, and reports a
  result back to the main thread.
- **Exclusive pass**: tests with `exclusive=True` get serialized into a
  separate queue run by a single worker, after the normal pass
  completes. Useful for tests that fight over a fixed resource (port,
  shared file, system-wide config).

A timeout watcher on the main thread sends `SIGTERM` (then `SIGKILL`)
when a job exceeds its limit; the exit code is mapped through
`_signal_map()` so the result line reads `SIGTERM:-15` rather than a
bare negative number.

The runner switches between two output modes. With a single worker and
normal verbosity it streams test stdout straight through, so an
interactive `blade test` of one target reads as if the test were run
directly. With multiple workers (or quiet mode) it buffers each test's
output and emits it as a single block after the test finishes, so
parallel runs don't interleave lines.

## 4. Results, summary, and the test history

A per-test `TestRunResult(exit_code, start_time, cost_time)` is recorded
for each job. The runner merges:

- Passed results: update the history, mark previously-failing tests as
  "repaired".
- Failed results: increment `fail_count`, record `first_fail_time` if
  this is a new failure, add to `new_failed_tests`.

The history file `<build_dir>/.blade.test.stamp` stores, per test, the
last `TestJob` (binary MD5, testdata MD5, env MD5, args) and the last
`TestHistoryItem` (run result, fail counters). It is a Python `repr()`
that loads back via `eval()`, so the schema stays human-readable and
forward-compatible with field additions.

A structured `blade-bin/.blade-test-summary.json` is also written every
run, with the same data partitioned into `passed` / `failed` /
`unchanged` / `repaired` / `new_failed` / `unrepaired` / `excluded`.
Outside tooling (CI dashboards, IDE integrations) reads from there
instead of parsing terminal output.

## 5. Incremental dedup of unchanged tests

The whole machinery in §4 and §5 — test history, the
`.blade-test-summary.json`, the `unchanged` / `unrepaired` buckets —
exists primarily for **large-monorepo CI ergonomics**: in a repo with
thousands of tests, one persistently-broken test must not gate the
whole CI pipeline, but it cannot disappear from the summary either.
The mechanism is a side-channel that keeps such tests visible (first-fail
time + retry count in `unrepaired`) so an owner is still nudged to fix
them, without holding the rest of the suite hostage.

`_run_reason()` decides whether a test must run:

- `EXPLICIT` — the test was named on the command line.
- `FULL_TEST` — `--full-test` overrides the dedup entirely.
- `ALWAYS_RUN` — target sets `always_run=True`.
- `BINARY` / `TESTDATA` / `ENVIRONMENT` / `ARGUMENT` — the corresponding
  MD5 changed since the last passing run. Environment uses
  `global_config.test_related_envs` (regex list) to decide which env
  vars matter, so a change to `EDITOR` doesn't invalidate every test.
- `STALE` — the last run is older than the cutoff (currently one day).
- `NO_HISTORY` — first run.
- `FAILED` / `RETRY` — the test failed last time and isn't covered by
  the unrepaired-skip policy.

If none of the above triggers, the test is silently skipped and counted
under "unchanged" in the summary. Tests that have been failing for a
while can be parked into the "unrepaired" bucket (with first-fail time
and retry count surfaced in the summary) rather than re-running every
build — important when one stubborn test holds up an otherwise green
suite.

## 6. Implementation details and UX optimizations

- **Runfiles + cwd-relative dylib resolution.** The single
  `runfiles/<build_dir>` symlink is what makes blade-built `.so`/`.dylib`
  files findable from a test's cwd without special install names or
  rpath. The cost of that symlink is one syscall per test; the benefit
  is that test execution works identically on Linux and macOS.
- **Exclusive tests are a separate pass.** Mixing exclusive tests into
  the parallel queue would have meant either capping parallelism for
  the whole pass or doing per-test gating. A second, single-worker
  pass is simpler and keeps the parallel path's logic simple.
- **The env MD5 with a configurable allow-list.** `test_related_envs`
  lets a workspace declare which env vars actually affect test
  results, so cosmetic changes (terminal program, shell PS1) don't
  invalidate the cache. Tests that genuinely depend on, say, `TZ` add
  it to the list.
- **Output capture vs streaming.** Auto-selecting based on worker count
  and verbosity makes the common single-target debugging case
  pleasant (no buffering) without sacrificing readable output on a
  thousand-test parallel run.
- **JSON summary alongside terminal output.** The summary file lets
  CI hook into structured results without grepping the test log; it
  carries timing, exit code, fail counts, and the "new failed" /
  "repaired" deltas that humans care about.
- **`unrepaired` policy.** Skipping known-broken tests by default
  (with a clear summary line) is a deliberate UX choice: a broken
  test should not hold up the rest of the suite, but the summary
  still says "still unrepaired, failing since X, retried N times" so
  it doesn't get forgotten.
- **Coverage cleanup.** When `--coverage` is set, `_clean_for_coverage()`
  removes the per-test runfiles build-dir symlinks at the end so the
  coverage tool walking the runfiles tree doesn't follow them into
  the real build dir.
