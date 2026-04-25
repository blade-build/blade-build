# Command Line Reference

## Basic Command Line Syntax

```bash
Blade <subcommand> [options]... [target patterns]...
```

## Subcommand

Subcommand is a subcommand that currently has:

- `build` Build specified targets
- `test`  Build and run tests
- `clean` Cleanup specified targets
- `dump`  Dump some useful information
- `query` Query target dependencies
- `run`   Build and run a single executable target

## Target Pattern

Target pattern list is a spaces separated list.

Target pattern is allowed in command line, some configuration items and target attributes.

Target pattern supported formats:

- `path:name` represents a target in the path
- `path:*` represents all targets in the path
- `path` same as above
- `path/...` represents all targets in the path, and recursively includes all subdirectories
- `:name` represents a target in the current directory

If path starts with `//`, it means it is a full path starts from the root of the [workspace](workspace.md).
Those whose name part is not a wildcard are called "direct targets".

If no target is specified, it defaults to all targets in the current directory (excluding subdirectories). If there is no BUILD file in the current directory, it will fail.
When you specify ... as the end target, if its path exists, it will not fail even if the expansion is empty.

Blade will search `BUILD` files recursively for the `...` target pattern, if some dirs should be
excluded from searching, you can put an empty `.bladeskip` under it.

If you have [ohmyzsh](https://ohmyz.sh/) installed, the bare `...` will be automatically
[expanded to `..\..`](https://github.com/ohmyzsh/ohmyzsh/wiki/Cheatsheet#directory), which needs to be written as `./...`.

## Filter by Target Tags

In Blade, each target also supports [tags attribute](build_file.md#tags).

You can filter the build targets with the tag filter expression through the `--tags-filter` option.

The filter expression consists of the full name of the tag, operators and parentheses.

-The full name of the tag: such as `lang:cc`, `type:test`
-Operator: support `not`, `and`, `or`
-Parentheses control priority

To select multiple tags in the same group at the same time, you can use the syntax of `group:name1,name2`, which is equivalent to `(group:name1 or group:name2)`.

Complicated expressions often cannot avoid spaces, and quotation marks are needed in this case.

Example:

- `--tags-filter='lang:cc'` to filter `cc_*` targets
- `--tags-filter='lang:cc,java'` to filters `cc_*` and `java_*` targets
- `--tags-filter='lang:cc and type:test'` to filter the `cc_test` target
- `--tags-filter='lang:cc and not type:test'` to filters `cc_*` targets other than `cc_test`

Filtering only apply to the target list expanded through the wildcatd target pattern on the command
line, and does not apply to direct targets and other targets that are dependent on it.
Any target that is dependent on the a unfiltered target will not be filtered out, regardless of
whether it matches the filtered condition or not.

To query which tags are available for the target to be filtered, you can use the `blade dump --all-tags` command:

```console
$ blade dump --all-tags ...
[
   "lang:cc",
   "lang:java",
   "lang:lexyacc",
   "lang:proto",
   "lang:py",
   "type:binary",
   "type:foreign",
   "type:gen_rule",
   "type:library",
   "type:maven",
   "type:prebuilt",
   "type:system",
   "type:test",
   "xxx:xxx"
]
```

## Subcommand Options

The options supported by different subcommands are different. Please run blade \<subcommand\> --help to view

Here are some common command line options

- `-m32,-m64` specifies the number of build target digits, the default is automatic detection
- `-p PROFILE` specifies `debug`/`release`, default is `release`
- `-k`, `--keep-going` encountered an error during the build process to continue execution (if it is a fatal error can not continue)
- `-j N`, `--jobs=N` N way parallel build (Blade defaults to parallel build, calculate the appropriate value by yourself)
- `-t N`, `--test-jobs=N` N-way parallel test, applicable on multi-CPU machines
- `--verbose` complete command output for each command line
- `–h`, `--help` show help
- `--color=yes/no/auto` Whether to turn on color
- `--exclude-targets` Comma separated target patterns, to be excluded from loading.
- `--generate-dynamic` Forces the generation of dynamic libraries
- `--generate-java` generates java files for proto_library and swig_library
- `--generate-php` generates php files for proto_library and swig_library
- `--generate-go` generates go files for proto_library
- `--gprof` supports GNU gprof
- `--coverage` supports generation of coverage and currently supports GNU gcov and Java jacoco

## Example

```bash
# Build all targets in the current directory, not including subdirectories
blade build

# Build all the targets in the current directory and subdirectories
blade build ...

# Build a target named `urllib` in the current directory
blade build :urllib

# Build all targets under the `app` direcotry, exclude its `sub` subdirectory
blade build app... --exclude-targets=app/sub...

# Build and test all targets from the WORKPACE root, common and all its subdirectories

blade test //common/...
blade test base/...

# Build and test the target named `string_test` in the base subdirectory
blade test base:string_test
```

## Command Line Completion

There is a simple command line completion after executing the [install](misc.md#install) command.
After installing [argcomplete](https://pypi.org/project/argcomplete/), you will get a complete command line completion.

### Install

```console
pip install argcomplete
```

For non-root installation, add the `--user` parameter.

### Enable

Modify `~/.bashrc`:

```bash
eval "$(register-python-argcomplete blade)"
```
