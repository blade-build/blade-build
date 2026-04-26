# Blade Frequently Asked Questions

## Runtime Environment Issues

### Platform Compatibility Problems

**Symptom:** Blade fails to execute and reports syntax errors on the target platform.

**Diagnostic Procedure:**

Blade v3 requires Python 3.10 or newer. Verify your Python installation:

```bash
python -V  # Check Python version
```

**Troubleshooting Steps:**

1. **Version Verification:** If an older Python is installed but errors persist, confirm `python -V` displays Python 3.10 or newer
2. **PATH Environment:** Update your PATH environment variable if necessary, or restart your terminal session
3. **Interpreter Identification:** Use `env python` or `which python` to identify the active Python interpreter

### Vim Syntax Highlighting for BUILD Files

**Issue:** Syntax highlighting fails when editing BUILD files in Vim.

**Resolution Checklist:**

1. **Installation Verification:** Confirm Blade installation completed successfully
2. **Syntax File Existence:** Check if `~/.vim/syntax/blade.vim` exists and references the correct file
3. **Configuration Validation:** Ensure `~/.vimrc` contains: `autocmd! BufRead,BufNewFile BUILD set filetype=blade`

**Escalation:** If the issue persists after these steps, contact the Blade development team for assistance.

### Alt Key Functionality Issues

**Issue:** Alt key functionality is not working as expected.

**Resolution:**

1. **Reinstallation:** Execute the Blade installation process again
2. **PATH Configuration:** Add `~/bin` to your user profile and restart your session

**Note:** This issue typically relates to terminal emulator configuration rather than Blade itself.

## Build System Issues

### Dependency Ordering Impact on Compilation Results

**Symptom:** Dependency order in `deps` affects compilation outcomes. For instance, `//common/config/ini:ini` produces different results based on its position in the dependency list.

**Root Cause Investigation:**

1. **Prebuilt Library Interference:** Compilation errors indicate `su.1.0` (a prebuilt library) positioned between dependencies
2. **Behavioral Variation:** `//common/config/ini:ini` compilation behavior changes relative to `su.1.0` placement
3. **Dependency Analysis:** Investigation reveals `su.1.0` depends on `//common/config/ini:ini` but lacks static library compilation
4. **Symbol Resolution Failure:** When `//common/config/ini:ini` follows `su.1.0`, GCC's symbol lookup order fails to resolve references

**Best Practices:**

- **Source Compilation Preference:** Compile projects from source whenever feasible
- **Prebuilt Library Minimization:** Limit prebuilt library usage; ensure they include complete dependency targets
- **Dependency Verification:** Validate dependency relationships when using prebuilt components

### ccache Error Message Caching Problem

**Symptom:** Compilation errors persist despite source file modifications, suggesting ccache may be caching error messages or warnings.

**Diagnostic Procedure:**

1. **Documentation Review:** Examine ccache documentation - direct mode may experience internal errors
2. **Configuration Isolation:** Test with modified configuration to isolate cache-related issues
3. **Preprocessing Analysis:** Header file changes not reflected in preprocessed output
4. **Path Resolution Discovery:** Identical header files exist in both `build64_release` and source directories
5. **Include Path Order:** Default ordering (`-Ibuild64_release -I.`) prioritizes `build64_release` directory
6. **File Placement Conflict:** Colleagues placed files in output directory while modifications occurred in project files

**Resolution:**

- **Include Path Validation:** Thoroughly review and validate include path configurations
- **Build Directory Management:** Maintain clear separation between source and build directories
- **Cache Management:** Implement proper ccache invalidation procedures when file conflicts occur

### Using Libraries Without Source Code

**Scenario:** Working with prebuilt libraries that lack source code.

**Solution:** Refer to the [[#cc_library]] documentation for prebuilt library configuration.

### Prebuilt Library with Shared Objects Only

**Problem Description:**
Prebuilt library contains only `.so` files, but dynamic library compilation is required.

**Technical Analysis:**

1. For `cc_library` targets requiring dynamic library compilation, provide only dynamic library files
2. `cc_plugin` targets require static library files

**Recommendations:**

- Prebuilt libraries should ideally provide both static and dynamic library variants
- Ensure you're using the latest version of Blade for optimal compatibility

### Converting Static Libraries to Dynamic Libraries

**Scenario:**
Only static libraries (.a files) are available, but dynamic library (.so) compilation is required.

**Technical Solution:**

Static libraries (.a) are archives containing object files (.o). Conversion to dynamic libraries involves:

```bash
# Extract object files from static library
ar -x mylib.a
# Create shared object from extracted object files
gcc -shared *.o -o mylib.so
```

**Additional Notes:**

- Blade provides automated conversion via the `atoso` script
- Dynamic libraries cannot be converted back to static libraries
- For third-party code, obtain both static and dynamic library variants whenever possible

### Using Specific GCC Version via Environment Variables

**Requirement:**
Compile projects using a specific GCC version.

**Implementation:**
Set environment variables to specify compiler paths:

```bash
CC=/usr/bin/gcc CXX=/usr/bin/g++ CPP=/usr/bin/cpp LD=/usr/bin/g++ blade targets
```

**Best Practices:**

- Ensure you're using the latest Blade version
- Maintain consistency across all compiler-related environment variables
- Use matching versions for compiler and linker components

### Persistent Compilation Errors After Code Modifications

**Issue Description:**
Blade compilation errors persist on CI machines even after error fixes and code updates from SVN.

**Root Cause Analysis:**

- File modification verification reveals potential copy issues
- CI machine file ownership: non-root user cannot overwrite root-owned files
- Error messages reference outdated file versions due to permission constraints

**Resolution:**

- Carefully manage file ownership during permission transitions
- Ensure proper file synchronization between development and CI environments

### SO Libraries with Embedded Path Information

**Issue Description:**
Blade-compiled shared object (.so) libraries contain path information, which complicates usage. Can this behavior be configured?

**Design Rationale:**

In large-scale projects with multiple sub-projects, libraries may be renamed across different contexts. Manual coordination of naming conflicts would be impractical.

Blade's approach of embedding path information in libraries provides a fundamental solution to naming conflicts. When utilizing these libraries, simply reference them using their full path identifiers.

### New Error Flags Not Functioning

**Issue Description:**
Recently updated Blade version, but new error flags are not taking effect during compilation.

**Troubleshooting Steps:**

- Verify Blade installation is current and properly updated
- Check if C++ program filters or ignores specific error flags
- Blade selectively applies error flags based on compiler support to avoid compilation failures
- Confirm GCC version meets minimum requirements for new flag features

**Resolution:**

- Upgrade GCC to a version that supports the required error flag functionality

### blade clean Command Not Removing Generated Files

**Issue Description:**
`blade clean` command fails to remove project-generated files.

**Resolution:**

Ensure command parameter consistency between build and clean operations:

- Use `blade clean -prelease` to clean files generated by `blade build -prelease`
- Use `blade clean -pdebug` to clean files generated by `blade build -pdebug`

**Verification:**

Double-check command syntax and parameter matching to ensure proper cleanup execution.

### How to display the command line of the build

I want to see the complete command executed during the build process.
The complete command line can be displayed by adding the --verbose parameter to the build.

### Publishing Precompiled Libraries

**Scenario:**
Distributing proprietary code as precompiled libraries while maintaining dependencies on open-source components.

**Original Library Configuration:**

```python
cc_library(
    name = 'security',
    srcs = 'security.cpp',
    hdrs = ['security.h'],
    deps = [
        '//common/base/string:string',
        '//thirdparty/glog:glog',
    ]
)
```

**Precompiled Distribution Configuration:**

```python
cc_library(
    name = 'security',
    hdrs = ['security.h'],
    prebuilt = True,  # Replace srcs with prebuilt flag
    deps = [
        '//common/base/string:string',
        '//thirdparty/glog:glog',
    ]
)
```

**Key Considerations:**

- External header files remain unchanged
- Dependency specifications must be preserved
- Only distribute libraries you have rights to publish as precompiled binaries
- Follow cc_library documentation for proper prebuilt library organization

### Unrecognized Options Error

**Error Example:** `unrecognized options {'link_all_symbols': 1}`

**Root Cause:**
Different target types support distinct parameter sets. This error occurs when attempting to use parameters not supported by the target type.

**Common Causes:**

- Parameter misapplication across different target types
- Spelling errors in parameter names

**Debugging Assistance:**
Blade's Vim syntax highlighting helps identify parameter errors during editing.

### Source File Ownership Conflict

**Error Example:**
`Source file cp_test_config.cc belongs to both cc_test xcube/cp/jobcontrol:job_controller_test and cc_test xcube/cp/jobcontrol:job_context_test`

**Technical Rationale:**

This violates C++'s [One Definition Rule](http://en.wikipedia.org/wiki/One_Definition_Rule), which prevents:
- Unnecessary duplicate compilation
- Potential compilation parameter inconsistencies

**Best Practice:**

Each source file should belong to exactly one target. For shared functionality:
1. Extract common code into a separate `cc_library`
2. Reference this library via `deps` in dependent targets
3. Maintain clear ownership boundaries between components

### Enabling C++11 Support

**Configuration:**
Add the following to your configuration file:

```python
cc_config(
    cxxflags='-std=gnu++11'
)
```

**Version Compatibility:**

- Refer to [GCC Online Documentation](https://gcc.gnu.org/onlinedocs/gcc/C-Dialect-Options.html) for additional dialect options
- For GCC versions predating C++11 standardization, use `"gnu++0x"` instead
- Modern GCC versions (e.g., GCC 6+) default to C++14, making this configuration optional

### Optimizing Disk Space Usage

**Challenge:**
Blade-built projects often involve large-scale codebases, resulting in substantial disk space consumption from build artifacts.

**Space Optimization Strategies:**

#### Debug Information Level Management

Blade defaults to including debugging symbols for enhanced debugging capabilities with tools like GDB. However, debug symbols constitute the largest portion of binary files.

**Configuration:**
```python
# Reduce debug information overhead
global_config(
    debug_info_level = 'no'
)
```

**Debug Level Options:**

- `no`: No debug information - minimal binary size, no symbol visibility in GDB
- `low`: Basic symbols - function names and global variables only
- `mid`: Standard debugging - includes local variables and function parameters (default)
- `high`: Comprehensive debugging - maximum symbol information including macros

**Trade-off:** Lower debug levels significantly reduce binary size but limit debugging capabilities.

#### DebugFission Optimization

**Feature:** DebugFission separates debug information from executable files, reducing binary size while maintaining debugging capabilities.

**Configuration Reference:**

- [`cc_config.fission`](config.md#cc_config) - Enable DebugFission functionality
- [`cc_config.dwp`](config.md#cc_config) - Package debug information files (.dwo) into debug packages (.dwp)
- [Using dwp files in package](build_rules/cc.md#using-dwp-files) - Integration of debug packages in deployment artifacts


#### Debug Information Compression

**Optimization:** Utilize GCC's [`-gz`](https://gcc.gnu.org/onlinedocs/gcc/Debugging-Options.html) option to compress debug information.

**Implementation Strategy:**

- Applicable during both compilation and linking phases
- For final executable size optimization, apply only during linking phase
- Compression/decompression overhead may impact build performance

**Global Configuration:**

```python
cc_config(
    ...
    cppflags = [..., '-gz', ...],
    linkflags = [..., '-gz', ...],
    ...
)
```

**Target-Specific Configuration:**

```python
cc_binary(
    name = 'xxx_server',
    ...
    extra_linkflags = ['-gz'],
)
```

**Compatibility Notes:**

- Requires [GDB versions supporting compressed debug symbols](https://sourceware.org/gdb/current/onlinedocs/gdb/Requirements.html)
- Older GDB versions or missing zlib configuration will prevent debug symbol reading

#### Debug Symbol Separation

**Challenge:** Reducing debug symbol levels or stripping symbols minimizes binary size but compromises debugging capabilities.

**Solution:** Implement [Separated Debugging Symbols](https://sourceware.org/gdb/onlinedocs/gdb/Separate-Debug-Files.html) to maintain debugging functionality while optimizing binary size.

**Benefits:**

- Maintains full debugging capabilities
- Reduces deployed binary footprint
- Enables efficient debugging symbol distribution

**Implementation:** Store debug symbols in separate files referenced by the main executable.

#### Dynamic Linking for Test Programs

**Configuration:**
```python
cc_test_config(
    dynamic_link = True
)
```

**Rationale:**

- Test programs are not deployed to production environments
- Dynamic linking significantly reduces disk space requirements
- Individual test cases requiring static linking can override with `dynamic_link = False`

**Benefits:**

- Substantial disk space savings for test artifacts
- Faster build times due to reduced linking overhead
- Flexible configuration for specific test requirements

#### Thin Static Library Generation

**Feature:** GNU ar supports 'thin' static library format, which differs from traditional static libraries by storing object file paths rather than actual object code.

**Benefits:**

- Significantly reduces disk space consumption
- Maintains build system efficiency

**Limitations:**

- Not suitable for distribution outside the build environment
- Compatible with Blade's internal library usage patterns

**Configuration:**

```python
cc_library_config(
    arflags = 'rcsT'  # Add 'T' flag for thin library generation
)
```

**Usage Context:** Ideal for internal build system libraries where distribution is not required.

### libstdc++ Library Not Found

**Error:** `cannot find -lstdc++`

**Solution:** Install the static version of libstdc++ library:

```bash
yum install libstdc++-static
```

**Context:** This error typically occurs when linking requires the static C++ standard library, which may not be installed by default on some systems.

### Compiler Process Termination Due to Resource Constraints

**Error:** `g++: Fatal error: Killed signal terminated program cc1plus`

**Root Cause:** System resources may be insufficient for Blade's default job count calculation.

**Resolution:** Reduce parallel job count using the `-j` parameter:

```bash
blade build -j4  # Use 4 jobs on an 8-core machine
```

**Best Practice:** Adjust job count based on available system memory and CPU resources to prevent out-of-memory conditions.

### Disk Space Exhaustion

**Error:** `No space left on device`

**Root Causes:**

- Output directory disk space depletion
- Temporary directory space constraints

**Resolution:**

- Clean up build artifacts and temporary files
- Configure alternative temporary directory via [TMPDIR](https://gcc.gnu.org/onlinedocs/gcc/Environment-Variables.html) environment variable

**Prevention:** Monitor disk usage during large builds and implement cleanup automation.

### Excluding Directories with External Build Files

**Scenario:** Skip directories containing build files from other build systems (e.g., Bazel).

**Solution:** Create an empty `.bladeskip` file in the target directory.

**Effect:** Blade will exclude the directory and all its subdirectories from build processing.

**Use Case:** Ideal for managing mixed build system environments or excluding third-party code with incompatible build configurations.
