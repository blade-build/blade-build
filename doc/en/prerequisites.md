# System Prerequisites and Dependencies

## Required Dependencies

Blade requires the following core dependencies for basic operation:

### Operating System Support

Linux is the primary, fully supported platform; macOS and Windows support is
experimental.

- **Linux:** All major distributions (Ubuntu, CentOS, Debian, etc.)
- **macOS** *(experimental)*: macOS 10.12+ with Xcode, or just the Xcode Command Line Tools
- **Windows** *(experimental)*: Windows 10/11 with Visual Studio, or just the Visual Studio Build Tools (MSVC toolchain)
  - Developer Mode is recommended (Settings → Privacy & security → For developers)
    to enable NTFS symlink support; if not enabled, `blade-bin` symlink is skipped

### Core Runtime Dependencies
- **Python:** Version 3.10 or newer
- **Ninja Build System:** Version 1.10+ (required as build backend)

## Optional Performance Enhancements

Blade integrates with the following tools for enhanced build performance:

- **ccache:** Version 3.1+ for compilation caching acceleration
- **distcc:** Distributed compilation support for large-scale builds

## Language-Specific Build Requirements

### C/C++ Development
- **GCC:** Version 4.0+ or compatible compiler (Clang supported), Linux/macOS
- **MSVC:** Visual Studio 2019/2022 Build Tools, Windows
- **Standard Libraries:** C++ standard library development packages

### Java Development
- **JDK:** Java Development Kit 1.6+ (OpenJDK or Oracle JDK)
- **Build Tools:** Maven or Gradle for Java project management

### Scala Development
- **Scala:** Version 2.10+ for Scala language support
- **SBT:** Scala Build Tool integration capabilities

### Code Generation Tools
- **SWIG:** Version 2.0+ (required for `swig_library` targets)
- **Flex:** Version 2.5+ (required for `lex_yacc` targets)
- **Bison:** Version 3.0+ (required for `lex_yacc` targets). Bison 2.x is no
  longer supported: its `-d` header omits the `yyparse` prototype, which
  downstream code needs. See the macOS note below.

## Platform-Specific Notes

### Linux Installation
- **Package Manager:** Use system package manager (apt, yum, dnf)
- **Development Tools:** Install build-essential or equivalent packages
- **Python Packages:** Ensure pip and setuptools are available

### macOS Installation
- **Xcode:** A full Xcode installation works, but the Xcode Command Line Tools alone are sufficient — you do not need the full IDE. Install just the tools with `xcode-select --install`
- **Homebrew:** Recommended for package management
- **Python:** Use Homebrew Python or system Python with pip
- **Bison** *(only for `lex_yacc_library` targets)*: macOS ships bison 2.3
  (frozen at GPLv2 and too old — see above). Install a current one with
  `brew install bison`. Homebrew keeps it keg-only (so it does not shadow the
  system bison), so add it to `PATH` ahead of `/usr/bin`:
  `export PATH="$(brew --prefix bison)/bin:$PATH"`. `flex` from Homebrew is fine
  as-is.

### Windows Installation

- **MSVC Toolchain:** A full Visual Studio installation works; the standalone [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022) are also sufficient — you do not need the full IDE. Either way, install the "MSVC v143" and "Windows SDK" components
- **Developer Mode:** Recommended (Settings → Privacy & security → For developers) to enable NTFS symlink support. When not enabled, the `blade-bin` symlink is skipped and a warning is emitted; this does not affect normal builds
- **Python:** Install Python 3.10+ from [python.org](https://www.python.org/downloads/)
- **Ninja:** Download from [ninja-build.org](https://ninja-build.org/) or install via `pip install ninja`
- **Git:** Required for SCM integration (revision embedding)
- **WinFlexBison** *(optional, for `lex_yacc_library` targets)*: Install via `winget install -e --id WinFlexBison.win_flex_bison`
- Add the Blade directory to `PATH`, or launch via `blade.bat`

## Version Compatibility Matrix

| Component | Minimum Version | Recommended Version | Notes |
|-----------|-----------------|-------------------|--------|
| Python | 3.10 | 3.12+ | v3 requires Python 3.10 or newer |
| Ninja | 1.10 | 1.11+ | Build backend; 1.10+ required for multi-output rules with depslog |
| GCC | 4.0 | 7.0+ | Clang 6.0+ also supported |
| JDK | 1.6 | 11+ | LTS versions recommended |
| Bison | 3.0 | 3.8+ | For `lex_yacc` targets; macOS stock 2.3 is too old (see macOS notes) |
| Flex | 2.5 | 2.6+ | For `lex_yacc` targets |

## Verification Commands

Verify installation of key dependencies:

```bash
# Check Python version
python --version

# Verify Ninja installation
ninja --version

# Confirm GCC availability
gcc --version

# Check Java installation
java -version
```
