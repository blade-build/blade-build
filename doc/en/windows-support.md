# Windows Toolchain Support

This document describes Windows support in Blade build system.

## Overview

Blade now supports building C/C++ targets on Windows using Microsoft Visual C++ (MSVC), Clang-CL, and MinGW-w64 toolchains.

## Supported Features

- ✅ Static library generation (.lib files)
- ✅ Dynamic library generation (.dll files with import libraries)
- ✅ Executable generation (.exe files)
- ✅ Header dependency tracking
- ✅ Incremental builds via Ninja backend
- ✅ Multiple toolchain support (MSVC, Clang-CL, MinGW)
- ✅ GCC to MSVC flag translation
- ✅ Windows-specific configuration options

## Setup Requirements

### Visual Studio (MSVC)

1. Install Visual Studio 2019 or 2022 with C++ toolchain
2. Run Visual Studio Developer Command Prompt or call `vcvarsall.bat`
3. Ensure `cl.exe`, `link.exe`, and `lib.exe` are in PATH

### MinGW-w64

1. Install MinGW-w64 via MSYS2 or standalone installer
2. Add MinGW bin directory to PATH
3. Set environment variables if needed

### Clang-CL

1. Install LLVM with Clang-CL frontend
2. Ensure `clang-cl.exe` is in PATH
3. Set up appropriate Windows SDK environment

## Configuration

### Basic Windows Configuration

```python
# BLADE_ROOT
windows_config(
    msvc_version='auto',  # auto, 2019, 2022
    cppflags=['/MD', '/EHsc'],
    cflags=[],
    cxxflags=[],
    linkflags=['/SUBSYSTEM:CONSOLE'],
    warnings=['/W3'],
    optimize={
        'debug': ['/Od'],
        'release': ['/O2'],
    }
)
```

### Configuration Options

- `msvc_version`: MSVC compiler version to use
- `windows_sdk`: Windows SDK version
- `visual_studio`: Visual Studio edition
- `cppflags`: Preprocessor flags (MSVC syntax)
- `cflags`: C-specific flags
- `cxxflags`: C++-specific flags
- `linkflags`: Linker flags
- `warnings`: Warning levels
- `optimize`: Optimization settings per profile

## Build Targets

### C/C++ Library

```python
cc_library(
    name='mylib',
    srcs=['lib.cpp', 'lib.c'],
    hdrs=['lib.h'],
    generate_dynamic=True  # Generate both .lib and .dll
)
```

### C/C++ Binary

```python
cc_binary(
    name='myapp',
    srcs=['main.cpp'],
    deps=['//lib:mylib']
)
```

## Flag Translation

Blade automatically translates common GCC flags to MSVC equivalents:

| GCC Flag | MSVC Flag | Description |
|-----------|------------|-------------|
| `-Wall` | `/W3` | Warning level 3 |
| `-Wextra` | `/W4` | Warning level 4 |
| `-O2` | `/O2` | Optimized build |
| `-O0` | `/Od` | No optimization |
| `-g` | `/Zi` | Debug information |
| `-fPIC` | *ignored* | Not needed on Windows |
| `-DNAME` | `/DNAME` | Preprocessor definition |
| `-Ipath` | `/Ipath` | Include directory |

## Architecture Support

Supported Windows architectures:

- `win32`: 32-bit Windows targets
- `win64`: 64-bit Windows targets
- `windows`: Alias for win64

## Build Artifacts

| Target Type | Unix | Windows |
|-------------|-------|---------|
| Static Library | `libname.a` | `libname.lib` |
| Dynamic Library | `libname.so` | `libname.dll` |
| Import Library | N/A | `libname.lib` |
| Executable | `app` | `app.exe` |

## Build Paths

Windows builds use different path structure:

```
build_win64_debug/
build_win64_release/
build_win32_debug/
build_win32_release/
```

## Troubleshooting

### Common Issues

1. **MSVC not found**: Ensure Visual Studio Developer Command Prompt
2. **PATH issues**: Check that compiler tools are in PATH
3. **Link errors**: Verify Windows SDK is installed and configured
4. **Missing includes**: Check INCLUDE environment variable

### Environment Variables

Required environment variables:

- `INCLUDE`: Windows SDK include paths
- `LIB`: Windows SDK library paths  
- `PATH`: Compiler and tool locations

### Debugging

Enable verbose output:

```bash
blade build --verbose
```

Check generated Ninja files:

```bash
# Examine generated build.ninja
cat build_win64_debug/build.ninja
```

## Limitations

Current implementation supports basic C/C++ targets. Some advanced features may not be available:

- Limited support for Fortran on Windows
- Some advanced linking features
- Cross-compilation from Linux to Windows (native only)
- Limited integration with Windows-specific tools

## Examples

### Simple Library

```python
cc_library(
    name='math',
    srcs=['math.cpp'],
    hdrs=['math.h']
)
```

### Application with Library

```python
cc_binary(
    name='calculator',
    srcs=['main.cpp'],
    deps=[':math']
)
```

### Custom Build Configuration

```python
windows_config(
    cppflags=['/MD', '/EHsc', '/DUNICODE'],
    warnings=['/W4'],
    linkflags=['/SUBSYSTEM:WINDOWS']
)

cc_binary(
    name='winapp',
    srcs=['winapp.cpp', 'resources.rc']
)
```

For more examples, see the `example/windows/` directory.