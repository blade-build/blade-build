# Command Line Reference

## Basic Command Line Syntax

```bash
blade <subcommand> [options]... [target patterns]...
```

## Subcommands

Blade supports the following subcommands:

- `build` - Build specified targets
- `test` - Build and execute tests
- `clean` - Clean up specified targets
- `dump` - Export useful information
- `query` - Query target dependencies
- `run` - Build and execute a single executable target

## Target Pattern Syntax

Target patterns are space-separated lists that identify build targets. These patterns are supported in command lines, configuration items, and target attributes.

### Supported Pattern Formats

- `path:name` - Specific target within a path
- `path:*` - All targets within a path
- `path` - Equivalent to `path:*`
- `path/...` - All targets within a path and all subdirectories recursively
- `:name` - Target in the current directory

### Path Resolution Rules

- **Full Paths:** Paths starting with `//` represent absolute paths from the workspace root
- **Direct Targets:** Patterns without wildcards in the name component are considered direct targets
- **Default Behavior:** When no target is specified, Blade builds all targets in the current directory (excluding subdirectories)
- **Empty Expansion:** Specifying `...` as the end target will not fail if the path exists, even if expansion results in no targets

### Directory Search Behavior

- **Recursive Search:** Blade recursively searches `BUILD` files for `...` target patterns
- **Exclusion Mechanism:** Place an empty `.bladeskip` file in directories to exclude them from recursive searches
- **Shell Compatibility:** With [ohmyzsh](https://ohmyz.sh/) installed, bare `...` expands to `..\..` - use `./...` instead

## Target Tag Filtering

Blade supports filtering build targets using tag expressions via the `--tags-filter` option. Each target supports [tags attribute](build_file.md#tags).

### Filter Expression Syntax

- **Tag Names:** Full tag names like `lang:cc`, `type:test`
- **Logical Operators:** `not`, `and`, `or`
- **Group Selection:** `group:name1,name2` syntax for selecting multiple tags within the same group (equivalent to `(group:name1 or group:name2)`)
- **Complex Expressions:** Use quotation marks for expressions containing spaces

### Filtering Examples

- `--tags-filter='lang:cc'` - Filter `cc_*` targets
- `--tags-filter='lang:cc,java'` - Filter `cc_*` and `java_*` targets
- `--tags-filter='lang:cc and type:test'` - Filter `cc_test` targets
- `--tags-filter='lang:cc and not type:test'` - Filter `cc_*` targets excluding `cc_test`

### Filtering Scope

Tag filtering applies only to targets expanded through wildcard patterns on the command line. Direct targets and their dependencies are not filtered. Any target dependent on an unfiltered target remains in the build regardless of its tag matching status.

### Tag Discovery

To discover available tags for filtering:

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

Different subcommands support different options. Run `blade <subcommand> --help` for complete option lists.

### Common Command Line Options

- `-m32`, `-m64` - Target architecture (32-bit/64-bit), defaults to automatic detection
- `-p PROFILE` - Build profile (`debug`/`release`), defaults to `release`
- `-k`, `--keep-going` - Continue execution after non-fatal errors
- `-j N`, `--jobs=N` - Parallel build jobs (Blade defaults to automatic parallelization)
- `-t N`, `--test-jobs=N` - Parallel test execution for multi-CPU systems
- `--verbose` - Display complete command output for each executed command
- `-h`, `--help` - Display help information
- `--color=yes/no/auto` - Enable/disable colored output
- `--exclude-targets` - Comma-separated target patterns to exclude from loading
- `--generate-dynamic` - Force generation of dynamic libraries
- `--generate-java` - Generate Java files for proto_library and swig_library
- `--generate-php` - Generate PHP files for proto_library and swig_library
- `--generate-go` - Generate Go files for proto_library
- `--gprof` - Enable GNU gprof profiling support
- `--coverage` - Generate code coverage reports (supports GNU gcov and Java jacoco)

## Usage Examples

```bash
# Build all targets in current directory (excluding subdirectories)
blade build

# Build all targets in current directory and all subdirectories
blade build ...

# Build specific target named 'urllib' in current directory
blade build :urllib

# Build all targets under 'app' directory, excluding 'sub' subdirectory
blade build app... --exclude-targets=app/sub...

# Build and test all targets from workspace root and common subdirectory
blade test //common/...
blade test base/...

# Build and test specific target in base subdirectory
blade test base:string_test
```

## Command Line Completion

Blade provides basic command line completion after installation. For enhanced completion functionality, install [argcomplete](https://pypi.org/project/argcomplete/).

### Installation

```console
pip install argcomplete
```

For non-root installations, add the `--user` parameter:

```console
pip install --user argcomplete
```

### Configuration

Add the following line to `~/.bashrc`:

```bash
eval "$(register-python-argcomplete blade)"
```
