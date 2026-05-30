# Development

## Code Structure

```text
src/
├── blade/              # Main source package
│   ├── main.py         # CLI entry point
│   ├── command_line.py # Argument parsing
│   ├── config.py       # Configuration loading (blade.conf, BLADE_ROOT, etc.)
│   ├── workspace.py    # Workspace discovery and management
│   ├── load_build_files.py  # BUILD file loading and DSL sandbox
│   ├── dependency_analyzer.py  # Topological sort and dependency resolution
│   ├── backend.py      # Backend build system generation (Ninja)
│   ├── build_manager.py     # Build orchestration
│   ├── ninja_runner.py      # Ninja invocation
│   ├── binary_runner.py     # Executing built binaries
│   ├── test_runner.py       # Test sandbox and execution
│   ├── test_scheduler.py    # Parallel test scheduling
│   ├── toolchain.py    # Compiler toolchain abstraction (GCC, MSVC, Clang)
│   ├── *_targets.py    # Build rule implementations (cc, java, py, go, etc.)
│   ├── target.py       # Base Target class
│   ├── build_rules.py  # Rule registration infrastructure
│   ├── dsl_api.py      # Safe `blade.*` DSL module exposed to BUILD files
│   ├── blade_types.py  # Shared type aliases (StrOrList, StrOrListOpt)
│   ├── util.py         # General-purpose helpers
│   ├── console.py      # Logging and diagnostic output
│   ├── config.py       # Configuration schema
│   └── inclusion_check.py  # Header dependency checking for C/C++
├── tests/
│   ├── unit/           # Unit tests (pytest, fast, offline)
│   └── (integration)   # See src/test/
└── test/               # Integration / end-to-end tests (pytest, require toolchain)
```

**Rule-target modules** (`*_targets.py`) each define one or more build rule types:

| Module | Rule(s) |
| --- | --- |
| `cc_targets.py` | `cc_library`, `cc_binary`, `cc_test`, `cc_plugin`, `prebuilt_cc_library`, `foreign_cc_library` |
| `java_targets.py` | `java_library`, `java_binary`, `java_test` |
| `py_targets.py` | `py_library`, `py_binary`, `py_test` |
| `proto_library_target.py` | `proto_library` |
| `go_targets.py` | `go_library`, `go_binary`, `go_test` |
| `scala_targets.py` | `scala_library`, `scala_test` |
| `cu_targets.py` | `cu_library`, `cu_binary`, `cu_test` |
| `gen_rule_target.py` | `gen_rule` |
| `lex_yacc_target.py` | `lex_yacc_library` |
| `resource_library_target.py` | `resource_library` |
| `windows_resources_target.py` | `windows_resources` |
| `package_target.py` | `package` |
| `sh_test_target.py` | `sh_test` |

## How It Works

### Loading Configuration

After Blade starts, it loads configuration files from multiple paths via `execfile`. These are Python source files that call predefined configuration functions, updating the configuration dict in `blade.config`.

Command-line options matching `global_config` keys are then applied with the highest priority.

### Loading BUILD Files

Blade expands from the command-line targets, executing `BUILD` files one by one via a restricted `execfile` sandbox. When BUILD code runs, it calls rule functions (e.g., `cc_library(...)`) which register targets into Blade's internal data structures.

BUILD files are loaded recursively for all transitive dependencies.

### Dependency Analysis

Blade performs a topological sort from the command-line target roots, producing an ordered build target list.

### Generating Backend Build Files

Each target generates backend actions (Ninja rules) which are written to a backend build file (e.g. `build.ninja`).

### Executing the Backend Build

Blade invokes the backend build tool (Ninja) to perform the actual build, then removes the generated build file.

### Running Tests

Test targets are built, then executed in parallel within sandbox environments. Results are collected and reported.

## Implementation Topics

In-depth documents on how individual subsystems are implemented, in
roughly the order they appear in a `blade build` invocation:

- [How configuration is loaded, layered, and consumed](develop/configuration.md)
- [How BUILD files are discovered, loaded, and registered](develop/build_file_loading.md)
- [Built-in functions and the `blade.*` DSL](develop/dsl_api.md)
- [How target visibility is implemented and enforced](develop/visibility.md)
- [Dependency analysis and ninja file generation](develop/dependency_analysis.md)
- [`gen_rule`: custom build steps and how other targets see them](develop/gen_rule.md)
- [How C/C++ programs are built](develop/cc_build.md)
- [How the C/C++ header dependency check (hdrs check) works](develop/hdrs_check.md)
- [How `proto_library` handles multi-language codegen](develop/protobuf_build.md)
- [How Java and Scala programs are built](develop/java_scala_build.md)
- [How Python targets are built and packaged](develop/python_build.md)
- [How `blade test` runs user tests](develop/test_execution.md)
- [How blade-build itself is tested](develop/self_testing.md)

## Testing

### Unit tests (`src/tests/unit/`)

Fast, offline tests that exercise individual modules. No toolchain or system dependencies required.

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src python -m pytest src/tests/unit/ -v
```

### Integration tests (`src/test/`)

End-to-end tests that drive real build/test cycles against fixture data in `src/test/testdata/`. Requires a working C/C++ toolchain (GCC, MSVC, or Clang).

```bash
src/test/runall.sh          # Run all integration tests
src/test/run.sh <test_name> # Run a single test (e.g. cc_library_test)
```

### Type checking

```bash
pip install -r requirements-dev.txt
pyright
```

## Adding a New Build Rule

1. **Create a target class** in a new or existing `*_targets.py` module. Inherit from `Target` (or a suitable subclass) and implement `generate()`.
2. **Define the rule-entry function** (e.g., `windows_resources()`) — this function normalizes BUILD-file-friendly types (`StrOrListOpt`) into `list[str]` via `var_to_list` / `var_to_list_or_none`, creates the target instance, and registers it via `build_manager.instance.register_target()`.
3. **Expose it in the DSL** by adding the function to `blade/__init__.py` and [dsl_api.py](src/blade/dsl_api.py).
4. **Add integration test data** under `src/test/testdata/<rule_name>/` with a `BUILD` file and source fixtures, then add a test class in `src/test/<rule_name>_test.py`.
5. **Update documentation** in [doc/en/build_rules/cc.md](doc/en/build_rules/cc.md) (or a new file for a new category).

### Key design patterns

- **`StrOrList` / `StrOrListOpt`** — Rule-entry functions accept `str | list[str]` unions for BUILD-file ergonomics. Always normalize to `list[str]` via `var_to_list()` (or `var_to_list_or_none()` for optional params) before passing to parent constructors.
- **Toolchain abstraction** (`toolchain.py`) — Platform-specific build details (compiler, linker, file suffixes) are encapsulated behind the `ToolChain` base class. Rule implementations query the toolchain rather than branching on `os.name`.
- **`blade.cc_toolchain`** — A read-only proxy exposed to BUILD files via the DSL for platform-aware decisions (file naming, capability queries).

## Debugging and Diagnostics

Most subcommands support `--stop-after` with options `{load, analyze, generate, build}` to stop after a specific phase:

```bash
blade build --stop-after generate
```

This stops after generating the backend build file (e.g. `build.ninja`), letting you inspect the generated output.

`--profiling` outputs a performance analysis report after execution. Combine with `--stop-after` to profile specific phases.

## CI

GitHub Actions workflows run on every PR and push to `master`:

| Workflow | Purpose |
| --- | --- |
| **Python package** | Unit tests + integration tests + pyright on Ubuntu (Python 3.10–3.14) |
| **Windows CI** | Unit tests + smoke tests + E2E on Windows (Python 3.10–3.13) |
| **CodeQL** | Security analysis |
| **Check Markdown links** | Link validation for documentation |

## Distribution

`dist_blade` in the repository root packages the source into a zip for deployment. Place it alongside the `blade` bootstrap script and `blade.conf`.

## Other Resources

Community analyses of Blade's internals (based on earlier versions, still informative):

- [On the design and implementation of C++Build in Blade](https://tsgsz.github.io/2013/11/01/2013-11-01-thinking-in-design-of-blade-cpp-build/)
- [Where is the sharp blade in the end](http://blog.sina.com.cn/s/blog_4af176450101bg69.html)
