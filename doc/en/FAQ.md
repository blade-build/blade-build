# Blade FAQ #

## Running environment ##

### Why can't blade run on my platform ###

description:
Run blade and report syntax error.

Solution process:

Blade needs to run python 2.7 or higher. Please use python -V to view the python version.

- Installed python 2.7 or reported an error, confirm that ptyhon -V sees the new version, configure the PATH environment variable if necessary or log in again.
- Use env python, which python and other commands to see which python command is used.

### vim No syntax highlighting when editing BUILD files ###

- First confirm whether it is installed by install
- Then check if ~/.vim/syntax/blade.vim exists and points to the correct file
- Then check if there is autocmd in the ~/.vimrc! BufRead, BufNewFile BUILD set filetype=blade

If the problem has not been resolved, please contact us.

### Why can't alt be used ###

description:
Alt can't use

Solution process:

 1. Re-execute the install
 - Add ~/bin to the user profile and log in again

## Building problem ##

### Why do the dependencies in the deps have different target sequences, and the compilation results are different ###

description:
//common/config/ini:ini The order of placement in a library's deps is different. It is not passed before, and passed to the back.

Solution process:

- View compilation error output, there is a library in the middle su.1.0 is a prebuilt library.
- //common/config/ini:ini The compilation result is different before and after this target.
- After viewing, su.1.0 relies on //common/config/ini:ini, but it is not compiled into a static library. and so
  //common/config/ini:ini. When it is placed behind it, gcc looks up in order to find symbols, but puts
  It can't be found before su.1.0, so the output is undefined reference.

In conclusion:

- It is recommended to compile the project as much as possible.
- Reduce the prebuilt project, the prebuilt library tries to complete the dependent target.

### ccache cached the error message, is there a problem with ccache ###

description:
There is an error in the compile prompt. After re-compiling in the source file, there is still an error. Is ccache buffering the alarm or error message, and there is no update?

Solution process:

 1. Check ccache manual, ccache may have an internal error in direct mode.
 - If you encounter this problem again, immediately modify the configuration to see if it is a cache itself.
 - At the same time, the results of pre-processing the cpp file are checked, and it is found that the header file modification is not reflected in the pre-processed file.
 - It should contain the path error. After searching, the same header file exists under build64_release, and build64_release is added by default.
-I, compile time by default -Ibuild64_realease -I.
In the build64_realease first find the header file, so find the header file of the same name, XFS colleagues put a file in this output directory, but the modification is
Your own project file.

in conclusion:

 * Check include path.

### I only have one library without source code, how to use it ###

Please refer to [[#cc_library]] for the prebuilt part.

### prebuilt library only .so files, I only need to compile the .so library ###

description:
The prebuilt library has only .so files, and I only need to compile the .so library.

Solution process:

 1. cc_library If you need to compile to a dynamic library, you only need to provide a dynamic library.
 - cc_plugin requires a static library.

in conclusion:

- So the prebuilt library is best to provide static and dynamic libraries.
- Upgrade to the latest blade.

### There is only a static library of passive code, but we need to compile the dynamic library ###

description:
Only static libraries are provided, but do we need to compile dynamic libraries?

Solution process:

 1. .a files are just archives of .o object files, so all you need to do is unpack the archive and repackage them as a shared object (.so).

```bash
ar -x mylib.a
gcc -shared *.o -o mylib.so
```

- We provide script auto-transfer, atoso
- so can't be converted to .a library.

Conclusion: When it comes to passive code, it's best to get both dynamic and static libraries.

### bladeSupport the gcc specified in the environment variable to compile the project ###

description:
I want to compile a project with a specific version of gcc.

Solution process:

 * CC=/usr/bin/gcc CXX=/usr/bin/g++ CPP=/usr/bin/cpp LD=/usr/bin/g++ blade targets

in conclusion:

 * Upgrade to the latest blade and note that the configuration of the environment variables is the same, that is, use the same version of the compiler and linker.

### My code has been modified, there is still a problem with blade compilation ###

description:
On the CI machine, the blade compiles with an error. After fixing the error, it is pulled from the svn, but it still prompts the same error.

Solution process:

- Check if the file is a modified copy.
- The file is rooted on the CI machine, and the user name of the colleague logging in to the machine is not root and cannot overwrite the original file.
- The file that indicated the error is an old file.

Conclusion:

- Pay attention to the owner of the file when switching permissions.

### Compiled SO library with path information ###

Description:
The `so` library compiled with Blade has path information, which is troublesome to use. Can you configure changes?

In a large project, different sub-projects, the library may be completely re-named, if the problem is manually coordinated, it is obviously not worth mentioning.
Therefore, when Blade uses the library, it always has path information, which fundamentally avoids this problem. You can also take the path when you use it.

### Why does the new error flag of Blade not work ###

Description:
Compiling the local project with the updated Blade found that the error flag didn't work?

Solution process:

- Check if the Blade is up to date.
- Check if the cpp program filters the error flag. If the error flag is not supported, Blade will not use it, otherwise the compiler will report an error.
- Check that the gcc version is too low.

Conclusion:

- Upgrade gcc.

### blade -c Can't clear files generated by the project ###

Description:
`blade clean` can't clear the files generated by the project

Solution process:

- Please check if the command is paired, clean `blade build -prelease` with `blade clean -prelease`, clean `blade build -pdebug` with `blade clean -pdebug`.

Conclusion:

- Check the command.

### How to display the command line of the build ###

I want to see the complete command executed during the build process.
The complete command line can be displayed by adding the --verbose parameter to the build.

### How do I publish a precompiled library ###

Some confidential code, I hope to release it as a library, but at the same time rely on non-confidential libraries (such as common), how to publish it?
Such a library:

```python
cc_library(
    name = 'secrity',
    srcs = 'secrity.cpp',
    hdrs = ['security.h'],
    deps = [
        '//common/base/string:string',
        '//thirdparty/glog:glog',
    ]
)
```

So released:
Modify the BUILD file and remove the srcs

```python
cc_library(
    name = 'secrity',
    hdrs = ['security.h'],
    prebuilt = True, # srcs changed to this
    deps = [
        '//common/base/string:string',
        '//thirdparty/glog:glog',
    ]
)
```

At the same time, the external header file remains unchanged. According to the cc_library introduction, the prebuild requires the organization of the library.
It's important to note that deps must remain the same, and don't publish libraries that are owned by you but not yours as pre-compiled libraries.

### unrecognized options What does this mean ###

For example unrecognized options {'link_all_symbols': 1}.
Different targets have different option parameters, and this error is reported if a parameter that is not supported by the target is passed. Possible cause is misuse of other targets
The parameters, or spelling errors, for the latter case, BLADE's vim syntax highlighting feature can help you see the error more easily.

### Source file xxx.cc belongs to both xxx and yyy What does this mean ###

For example, Source file cp_test_config.cc belongs to both cc_test xcube/cp/jobcontrol:job_controller_test and cc_test xcube/cp/jobcontrol:job_context_test?

In order to avoid unnecessary repetitive compilation and possible different compilation parameters, it violates C++'s [one-time definition rule](http://en.wikipedia.org/wiki/One_Definition_Rule).
Usually each source file should belong to only one target. If a source file is used by multiple targets, it should be written as a separate cc_library and depend on this library in deps.

### How to open C++11 ###

Edit the configuration file and add:

```python
cc_config(
    cxxflags='-std=gnu++11'
)
```

See [GCC Online Documents](https://gcc.gnu.org/onlinedocs/gcc/C-Dialect-Options.html) to see other values。Some version
of GCC was released before C++11 stdndard，maybe you should use ”gnu++0x“ to instead。

For higher version GCC，such as GCC 6, C++14 is already the default std value, this configuration item maybe become unnecessnary.

### Compiled results take up too much disk space ###

Projects built with blade are often large-scale projects, so the result files often take up more disk space. If it is a
problem, you can try to optimize them in the following ways.

#### Reduce debug information level ####

Blade compiles the code with debugging symbols defaultly, so that when you use some tools such as gdb to debug, you can
see the names of functions and variables, but the debugging symbols are usually the largest part of the binary file.
By reducing the level of debugging symbols, the size of the binary file can be significantly reduced, but it also makes
the program more difficult to debug.

```python
# Reduce the overhead of debug information
global_config(
    debug_info_level = 'no'
)
```

Description:

- `no`: no debug information. When debugging with gdb, you can not see the symbolic names for functions and variables, etc
- `low`: low debug information, you can only see the function name and global variables
- `mid`: medium, you can see more symbols than `low`, includes local variables and function parameters
- `high`: highest, contains more debug information, such as for macros

The default value is `mid`.

#### Enable DebugFission ####

For DebugFission configuration details, please refer to:
- [`cc_config.fission`](config.md#cc_config) - Enable DebugFission feature
- [`cc_config.dwp`](config.md#cc_config) - Package dwo files into dwp files
- [Using dwp files in package](build_rules/cc.md#using-dwp-files) - How to include dwp files in deployment packages


#### Compress debug information ####

You can use the [`-gz`](https://gcc.gnu.org/onlinedocs/gcc/Debugging-Options.html) option of GCC to compress debug information.
This option can be used in both compile and link phases.
If you only want to reduce the size of the final executable file, suggest only use it in the the link phase, because
compression and decompression will reduce the build speed.

This option can be used globally in the configuration:

```python
cc_config(
    ...
    cppflags = [...,'-gz', ...],
    linkflags = [...,'-gz', ...],
    ...
)
```

It can also be used for a specific single target:

```python
cc_binary(
    name ='xxx_server',
    ...
    extra_linkflags = ['-gz'],
)
```

NOTE: Only [newer version of gdb supports reading compressed debugging symbols](https://sourceware.org/gdb/current/onlinedocs/gdb/Requirements.html),
if the gdb version is too low or `zlib` is not configured, the debugging information cannot be read correctly.

#### Separate Debugging Symbols ####

Lowering the level of debugging symbols or using strip to delete debugging symbols can reduce the size of the binary file,
but it also makes the program difficult to debug.
Splitting the debugging symbols into separate files through [Separated Debugging Symbols](https://sourceware.org/gdb/onlinedocs/gdb/Separate-Debug-Files.html) is a compromise.

#### Link test programs dynamically ####

```python
cc_test_config(
    dynamic_link = True
)
The test program is not used for publishing. Dynamic linking can reduce a lot of disk overhead. If a specific test dynamic link fails, you can specify dynamic_link = False for it separately.
```

#### Generate "thin" static library ###

Gnu ar supports the generation of static libraries of type 'thin', which is different from regular static libraries. The thin static library only records the path of the .o file, which can reduce the space occupation to a large extent.
However, this kind of library can't be used for publishing. Fortunately, in the scenario of using blade, static libraries are generally used only inside the build system.

The practice is to modify the cc_library_config.arflags parameter, plus the `T` option:

```python
cc_library_config(
    arflags = 'rcsT'
)
```

### cannot find -lstdc++ ###

Maybe you need to install a static version of libstdc++:

```bash
yum install libstdc++-static
```

### g++: Fatal error:Killed signal terminated program cc1plus ###

Maybe your devbox is not powerful enough to support defaultly calculated number of jobs, retry with `-j <smaller-job-number>` parameter, such as using `blade build -j4` in a 8 cores machine.

### No space left on device ###

The output disk is full. Besides the output directory, the temporary directory is often a root cause, you can try to clean it or modify the [TMPDIR](https://gcc.gnu.org/onlinedocs/gcc/Environment-Variables.html) environment variable to change it.

### How to skip some directories contains foreign `BUILD` files (such as from bazel) ###

Place an empty `.bladeskip` file under this directory, it and its subdirectories will be skipped.
