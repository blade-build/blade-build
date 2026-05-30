# How Python targets are built and packaged

A `py_binary` ends up as a **shell wrapper + a sibling `.zip`** archive:
the zip is the application bundle, and the wrapper prepends it to
`PYTHONPATH` and invokes `python -m <entry>`. No PEX, no PyInstaller —
just standard Python `zipapp`-style loading. The whole pipeline is
intentionally small and predictable.

| File | Role |
| --- | --- |
| `src/blade/py_targets.py` | `PythonLibrary`, `PythonBinary`, `PythonTest` |
| `src/blade/builtin_tools.py` | The Python zip assembler and wrapper-script emitter |
| `src/blade/backend.py` | `pythonlibrary` / `pythonbinary` ninja rules |
| `src/blade/test_scheduler.py` | Test launching for `py_test` (uses the same wrapper) |

## 1. Targets

- **`py_library`** — emits a `.pylib` metadata file: a Python literal
  containing the library's source files and their MD5 digests, plus the
  package base directory. No executable output; this is purely the unit
  of information a `py_binary` later collects.
- **`py_binary`** — `PythonLibrary` plus a packaging step: produces
  `<name>.zip` (the bundle) and `<name>` (the shell wrapper).
- **`py_test`** — `PythonBinary` with `run_in_shell=True`. The test
  framework (unittest, pytest, ...) is whatever the user's `main` module
  invokes; blade does not impose a runner.

## 2. Source and dep collection

`base='//path'` on a target controls how source paths get mapped to
import names. With `base='//proto'`, a source `proto/foo/bar.py` becomes
`foo.bar` at import time. `_get_entry()` computes the dotted name for the
`main` attribute by stripping `.py` and rewriting separators.

Sources can be raw `.py` files, `.egg`s, or `.whl`s. The `.pylib` records
each as a `(path, md5)` pair; a binary then walks `expanded_deps` and
reads every dep's `.pylib` for its file list. There is intentionally no
native-extension story: deps that produce `.so`/`.dylib` outputs (e.g. a
`cc_library` referenced from a Python target) are not pulled in by this
mechanism.

## 3. `py_binary` packaging

The builtin `python_binary` tool in `builtin_tools.py` does the actual
assembly:

1. Read each input `.pylib` and re-derive each source's arcname relative
   to the configured base.
2. Filter against the target's `exclusions` (fnmatch patterns) — useful
   for keeping test fixtures or platform-specific files out of the bundle.
3. `.egg`/`.whl` inputs are unzipped and re-zipped on the fly, dropping
   metadata directories (`.dist-info/`, `EGG-INFO/`) and pre-built
   bytecode (`.pyc`); bytecode is generated at runtime instead, which
   sidesteps cross-Python-version mismatches.
4. Track which directories saw at least one source; inject empty
   `__init__.py` for any directory that's part of the namespace path but
   doesn't already have one (so namespace packages work without users
   adding stubs by hand).
5. Write the zip via `write_if_changed` so unchanged content preserves
   mtime — ninja's `restat` can then prune downstream rules that depended
   on this bundle.

The wrapper is platform-specific but very small:

- POSIX (`#!/bin/sh`): `PYTHONPATH="$DIR/$NAME.zip:$PYTHONPATH" exec
  "$BLADE_PYTHON_INTERPRETER" -m <entry>`.
- Windows (`.bat`): the analogous `set PYTHONPATH=...;%PYTHONPATH%`
  followed by `python -m <entry>`.

`BLADE_PYTHON_INTERPRETER` lets the running shell/CI pick a specific
interpreter version without rebuilding the bundle; the wrapper defaults
to the host `python3`/`python`. So a `py_binary` built once can be
launched on multiple Python versions, as long as the user's code is
compatible.

## 4. Test execution

`py_test` sets `run_in_shell=True`. The test scheduler
([test execution](test_execution.md)) sees that flag and launches the
wrapper script via the shell — which then dispatches into `python -m
<entry>`. blade contributes no test framework: the test author's `main`
module is what calls `pytest.main()` / `unittest.main()` / their own
runner. Exit code determines pass/fail, and the runfiles / testdata
plumbing is the standard one all test rules share.

## 5. Implementation details and UX optimizations

- **No `.pyc` in the bundle.** Bytecode is generated at first import
  into the user's runtime cache; the bundle stays portable across
  Python minor versions. The cost is a one-time per-process bytecode
  generation; the benefit is bundles that don't have to be rebuilt per
  interpreter.
- **`write_if_changed` zip.** If the assembled content didn't change
  (typical of touched-but-no-content-changed BUILD edits), the zip's
  mtime is preserved so any dependent rules see no input change. Most
  rebuilds of an upstream test data file have zero downstream cost.
- **Source-fingerprint MD5 in `.pylib`.** ninja's depfile catches
  filesystem changes, but the explicit MD5 in `.pylib` makes the
  library's identity content-based rather than mtime-based — useful for
  catching `touch`-only changes that shouldn't trigger work.
- **`base` is the only knob to learn.** Most other build systems require
  a sources-vs-packages map; here a single `base` plus normal directory
  layout is enough. The entry computation is then a pure path-to-dotted
  rewrite, and the runtime side is just one extra `PYTHONPATH` entry.
- **Fresh-machine launchability.** The pair (`wrapper`, `wrapper.zip`)
  is self-contained as long as a Python interpreter is on `$PATH`. No
  install step.
- **What blade does not do.** It does not bundle native extensions, does
  not perform a `pip install` of declared requirements, and does not
  rewrite shebangs — these are deliberately left to project conventions
  (vendor the wheels into a `py_library`, or rely on the runtime
  environment).
