# DSL and API Module

## DSL Language

For more stable build processs, blade's DSL is designed to be a restricted Python language that prohibits some builtin
functions and keywords, include but not limited to:

- `exec`, `execfile` and `eval` To improve the consistency of BUILD files.
- `import` Use the built-in `blade` module instead
- `print` Use the functions in `blade.console` module instead

Some builtin functions are restricted.
- `open` only read mode is allowed

To use some common additional functions, such as `os.path.join`, you need to use similar sub-modules in the `blade` module.
If you want to add more appropriate modules, please make an Issue.

To allow unrestricted python in existing `BUILD` files, set the `global_config.unrestricted_dsl_dirs = [...]`,
to disable DSL restriction globally, set the `global_config.restricted_dsl = False`.

## `blade` Module

The global Blade API module, accessed through `blade.`, includes:

- `current_source_dir()` function: The directory where the current BUILD file is located (relative to the root directory of the workspace)
- `current_target_dir()` function: The output directory where the current BUILD file is located corresponds to (relative to the root directory of the workspace)
- `config` submodule: Read blade configuration information
- `console` submodule: Output diagnostic information
- `re` submodule: The python regex library
- `path` submodule: a Restricted subset of `os.path`

### `blade.config` Submodule

Access configuration information, including:

- `get_section()` function: Get the content of a configuration section, such as `cc_config`, which can be read through the `get` method
- `get_item()` function: Get a specific configuration item, such as `blade.config.get_item('cc_config','cppflags')`

### `blade.console` Submodule

Output diagnostic information, including:

- `debug()` function: Output debugging message, which is not displayed by default, only output to the screen after using the `--verbose` option
- `info()` function: Output informational message
- `notice()` function: Output some notiable message
- `warning()` function: Output warning message
- `error()` function: Output error message, which will cause the build to fail

### `blade.path` Submodule

A subset of the `os.path` module, including `abspath()`, `basename()`, `dirname()`, `exists()`, `join()`, `normpath()`, `relpath ()`, `sep`, `splitext()`.

### `blade.util` Submodule

Some auxiliary functions, including:

- `var_to_list()` function: If type of the argument is `str`, turn it into `list` contains a single element

### `blade.workspace` module

Get some information about the current [workspace](workspace.md), including:

- `root_dir()` function: Returns the directory of the current root workspace
- `build_dir()` function: Returns the name of the build subdirectory under the workspace, such as `build64_release`
