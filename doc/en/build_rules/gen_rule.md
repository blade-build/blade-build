# Custom Build Rules

## gen\_rule

Used to customize your own construction rules, parameters:

- src_exts: list(str) The list of file extensions allowed in `src`.

  Without `.`, for example, `['m4']` can match `config.m4`. If it is empty, it means that all types of files are allowed.
  Note that empty strings match files without extensions, such as `['h','']` matches `vector.h` and `vector`.

- outs: list, output file list
- cmd: str, the called command line, may contain the following variables, which will be replaced with actual values before running:
    - $SRCS, space-separated list of source file names, relative to WORKSPACE
    - $OUTS, space-separated list of output files, relative to WORKSPACE
    - $SRC\_DIR, the directory where the input file is located
    - $OUT\_DIR, the directory where the output file is located
    - $FIRST\_SRC, first input file path
    - $FIRST\_OUT, the path of the first output file
    - BUILD\_DIR, The root output directory, such as build[64,32]\_[release, debug]
  - `$(location target)` and `$(location target label)` — replaced with the output
    file path(s) of the referenced target. The optional `label` parameter specifies
    a particular output (e.g. `$(location //bin:server bin)`). Commonly used in
    `gen_rule.cmd`, `testdata`, `package`, and `sh_test`. Example:

    ```python
    gen_rule(
        name = 'copy_binary',
        cmd = 'cp $(location //server:server) $OUT_DIR/server',
        outs = ['server'],
    )
    ```

- cmd\_name: str, the name of the command, used to display in simplified mode, the default is `COMMAND`
- generate\_hdrs: bool, indicates whether this target will generate C/C++ header files other than the file names already listed in `outs`.
  If a C/C ++ target depends on the gen\_rule target that generates header files, then these header files need to be generated before compilation can begin.
  gen\_rule will automatically analyze whether there are header files in `outs`, so there is no need to set it if all of the headers are listed in `outs`.
  This option will reduce the parallelism of compilation, because if a target can be divided into mutiple stages, such as:
  - generating source code (including header files)
  - compiling
  - generating library
  When the header file list is given accurately, after the first stage is generated, other targets can be built without waiting the whole target is built.
- export\_incs: list, indicates the include path for generated header files, similar to `cc_library.export_incs`, but NOTE its relative to the target dir.
- cleans: list, specify the additional paths to be deleted when the `clean` command is executed, which can be files or directories, relative to the `$OUT_DIR`.
  The files in `outs` will always be deleted during `clean`. But if some additional files or directories are generated, including them in `cleans` can ensure that they can be deleted during clean.
- heavy: bool, indicates this a "heavy" target, that is, it will consume a lot of CPU or memory, making it impossible to parallel with other tasks or too much.
  Turning on this option will reduce build performance, but will help reduce build failures caused by insufficient resources.

Example:

```python
gen_rule(
    name='test_gen_target',
    cmd='echo what_a_nice_day;touch test2.c',
    deps=[':test_gen'],
    outs=['test2.c']
)
````

NOTE:

 `gen_rule` only writes `outs` files in the subdir of BUILD\_DIR, but when you use `gen_rule`
to generate source code and want to reference the generated source code in other targets, just
consider them as if they are generated in the source tree, without the BUILD\_DIR prefix.

- `srcs` can be empty, but `outs` and `cmd` cannot be empty.
- `gen_rule` should only generate output files in the corresponding result output directory, and will not pollute the source code tree. But if you reference in other targets
  which generating source files with `gen_rule`, it is only necessary to assume that these files are generated in the source code directory, without considering the result directory prefix.
- After the command is executed, the correct exit code must be returned, 0 means success, other values mean failure
- Successful commands should not output irrelevant information, and failed commands should output concise and useful error messages.
- When you need to use `$` in a command, such as expanding environment variables or executing command substitution, you need to double write it as `$$`, such as `$$(pwd)`.
- Multiple duplicate or similar gen_rules should be considered as extensions and maintained in a separate `bld` file through [include](../functions.md#include)
  Functions are introduced to reduce code redundancy and better maintenance.
