# Upgrade to V2

## Features

There are many improvement in V2, include performance,new features, code refactoring. You can get such benefits from V2:

- Full functional java and scala building
- Header files are included in dependency mangement.
- Support describe libraries which built by other build systems such as Autotool and CMake by using the new `foreign_cc_library` rule
- Support custom extensions. you can write you own extension and using the `load` function to load it
- Many performance optimizations
- Better diagnostic message include BUILD file path and line number, you can jump into BUILD files in editors now.
- Support self profile and diagnostic
- Support show slow build targets and tests
- Support quiet mode (by the `--quiet` option), just show progress bar when nothing is wrong.
- Better `clean` sub command
- Complete English documents.

## Possible Problems

### Python Version

V2 only support python 2.7 and 3.x, no longer support old versions. And for python 3.x, only 3.6 and 3.9 were tests.

### Ninja

Blade is a "meta" build system, it must depends on a backend build system.
The initial version use `SCons` as its backend. But after years, we found that `ninja` is much faster than SCons.
So in V2, we only support ninja as our backend build system.

To upgrade to V2, you muse install [ninja](https://ninja-build.org/), by either package manager or downloaded binary.

### Header Files Dependency Check

Header file are included in dependency management in V2 defaultly.
If you use V2 to build old projects which were built by V1.x, many diagnostic errors will occur.
You can fix or suppress these legancy errors. or turn off this check totally (strongly discouraged!).
See [config](config.md) and [cc rules](build_rules/cc.md) for details.

### Target Visibility Control

[Visibility](build_file.md) of the target is private by default. Targets is only visible to other
ones in same `BUILD` file defaultly. This feature can be disabled [globally](config.md#global_config),
or only check new added build targets by exempting the existing ones.

### Prebuilt cc_library path

In 1.0, the search directories of prebuilt binary libraries were hard-coded with directory names like `lib64_debug`, `lib64_release`.
We have observed that in practice such libraries are rarely provided and need to be distinguished from `debug`/`release` versions,
so in 2.0, the part involving build mode has been removed by default.

If you need to be compatible with the original behavior, you can set the [libpath_pattern](build_rules/cc.md#prebuilt_cc_library) attribute.
If global compatibility with the original behavior is needed, you can modify the global configuration item
[cc_library_config.prebuilt_libpath_pattern](config.md#cc_library_config).
