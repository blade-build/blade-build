# Installation Guide

## Automated Installation

Execute the following command in your terminal to install Blade automatically:

```console
curl https://blade-build.github.io/install.sh | bash
```

**Installation Process:**
- **Source Download:** Blade is cloned to `~/.cache/blade-build`
- **Symbolic Link Creation:** A symbolic link is created at `~/bin/blade`
- **Command Availability:** The `blade` command becomes available system-wide

## Manual Installation

### Installation Method

Execute the installation script to install Blade under `~/bin`:

**Installation Characteristics:**
- **Symbolic Link Installation:** Uses symbolic links for flexible updates
- **Source Preservation:** Original checkout directory must remain intact
- **Backend Dependency:** Requires [Ninja](https://ninja-build.org/) as the build backend

### Python Version Support

**Supported Python Versions:**
- **Python 3.10+:** Required minimum version (tested on 3.10 through 3.14)

Older versions (Python 2.7 and Python 3.x prior to 3.10) are no longer supported by Blade v3. For legacy environments, use the `2.x` LTS branch.

## Post-Installation Verification

### Command Execution Test

Verify installation by running Blade without arguments:

```bash
$ blade
usage: blade [-h] [--version] {build,run,test,clean,query,dump} ...
blade: error: too few arguments
Blade(error): Failure
```

### PATH Configuration

If the command is not found, ensure `~/bin` is in your PATH environment variable:

Add the following line to `~/.profile`:

```bash
export PATH=~/bin:$PATH
```

**Activation:** Relogin or restart your terminal session to apply changes

## System Requirements

### Required Dependencies

- **Ninja Build System:** Required for backend build operations
- **Python Interpreter:** Python 3.10 or newer
- **Development Tools:** Standard C/C++ toolchain (GCC/Clang)

### Optional Dependencies

- **ccache:** For build acceleration through caching
- **argcomplete:** Enhanced command-line completion support

## Troubleshooting

### Common Issues

- **Command Not Found:** Verify PATH configuration and symbolic link creation
- **Permission Errors:** Ensure `~/bin` directory has appropriate permissions
- **Python Version Conflicts:** Confirm compatible Python version availability

### Support Resources

- **Documentation:** Refer to Blade documentation for detailed troubleshooting
- **Community Support:** Access GitHub issues for community assistance
- **Version Compatibility:** Check version-specific requirements before installation
