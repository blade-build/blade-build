# Writing BUILD Files

Blade utilizes BUILD files (all uppercase) to define build targets. Each BUILD file specifies the source files, dependencies, and configuration properties for one or more targets using declarative function calls.

## BUILD File Example

Example: `common/base/string/BUILD`

```python
cc_library(
    name = 'string',
    srcs = [
        'algorithm.cpp',
        'format.cpp',
        'concat.cpp',
    ],
    hdrs = [
        'algorithm.h',
        'format.h',
        'concat.h',
    ],
    deps = ['//common/base:int'],
)
```

BUILD files employ a declarative syntax where developers specify target names, source files, and dependencies without needing to define compilation or linking commands explicitly.

## BUILD Language

See [BUILD Language](dsl.md).

## Style Suggestion

* Indented 4 spaces, do not use tab characters
* Always use single quotes (`'`) rather than double quotes (`"`)
* Keep target names in lowercase
* The file names in src are in alphabetical order
* Deps writes the dependencies (:target) in this directory first, and then writes (//dir:name) in
  other directories, in alphabetical order
* When placing 1 parameter per line, the last parameter also ends with a comma (`,`) to reduce the
  number of lines affected when adding or deleting parameters
* Put an empty line between different targets, can also put comments before it
* An empty # after the comment #, such as # This is a comment

## Common Attributes

Blade uses a set of target functions to define targets. The common properties of these targets are:

### name

string, together with the path to become the unique identifier of the target, also determines
  the output name of the build

### srcs

list or string, the source file needed to build the object, usually in the current directory,
or in a subdirectory relative to the current directory.

We also provide a [glob](functions.md#glob) function to generate the source files list.

### deps

list or string, other targets on which the object depends.

The allowed formats:

* `'//path/to/dir:name'` Target in other directories, path is the path from BLADE_ROOT, and name is
  the target name to be relied upon. When you see it, you know where it is.
* `':name'` The target, path in the current BUILD file can be omitted.
* `'#name'` System library. Write # with the name directly, such as `#pthread`, `#z` respectively
  equivalent to link `-lpthread` and `-lz` on the command line, but will be passed to other targets
   that depend on this library.

### visibility

list or string of build target pattern, control visibility to the listed targets,
there is a special value: `PUBLIC`, means visible to everyone, the targets in the same directory
are always visible to each other.

Examples:

```python
visibility = []                                            # Private, only visible to the current BUILD file
visibility = ['PUBLIC']                                    # Visible to every one
visibility = ['//module1:program12','//module1:program2']  # Only visible to these two targets
visibility = ['//module2:*']                               # Only visible to the targets under the module2 directory, but not to its subdirectories
visibility = ['//module3:...']                             # Only visible to the targets under the module3 directory and all its subdirectories
```

In Blade 1, all targets are `PUBLIC` by default. In Blade 2, in order to adapt to the dependency
management of larger projects, it is adjusted to be private by default.

For targets that already exist in an existing project, they can be set to `PUBLIC` through the
[`legacy_public_targets`](config.md#global_config) configuration item, which only requires
explicit settings for newly added targets.

### tags

The tags of the target can be set and queried by the user. Blade sets some default tags for each target.

The tags must consist of two parts, the group name and the name, separated by colons.

Blade presets some tags for various build targets:

-By programming language: `lang:cc`, `lang:java`, `lang:py`, `lang:proto` etc.
-By type: `type:binary`, `type:test`, `type:library`
-Other extra attributes: `type:prebuilt`

For example, the `cc_library` target automatically has the `['lang:cc','type:library']` attribute.

The default tags has not yet developed a detailed naming convention, so it may change in the future.

The biggest use of tags is to query and filter on the command line, such as only building targets in
certain languages, excluding certain types of targets, and so on.
See [Command Line Reference](command_line.md).

## Build Rules

* [Building C/C++ Goals](build_rules/cc.md)
* [Building protobuf and thrift](build_rules/idl.md)
* [Building Java](build_rules/java.md)
* [Building Scala](build_rules/scala.md)
* [Building Python](build_rules/python.md)
* [Building Lex and Yacc](build_rules/lexyacc.md)
* [Build SWIG](build_rules/swig.md)
* [Bash test](build_rules/shell.md)
* [Custom Build Rules](build_rules/gen_rule.md)
* [File Packaging](build_rules/package.md)

## Other Features

* Some [functions](functions.md) which can be called in BUILD files
* You can create and use your custom functions and rules via [extension](build_rules/extension.md)
  mechanism
