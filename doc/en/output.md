# Blade Output System

## Terminal Display Features

Blade provides enhanced terminal output with the following characteristics:

- **Color-Coded Output:** Build processes are color-highlighted for improved visual distinction
- **Error Highlighting:** Error messages are prominently colored for quick identification
- **Minimal Output:** Command execution details are suppressed unless errors occur, reducing screen clutter
- **Log File Recording:** All output is simultaneously written to `blade-bin/blade.log` for comprehensive logging

## Generated Artifacts

### Default Build Behavior

- **Architecture:** Generates native architecture executables by default
- **Architecture Selection:** Specify 32/64-bit targets using `-m32`/`-m64` flags
- **Build Profile:** Defaults to release builds; use `-p debug` for debug versions
- **Scope:** Builds current directory targets by default
- **Dependency Management:** Automatically rebuilds external module dependencies when required

### Recursive Build Capability

Build all targets in current directory and subdirectories:

```bash
blade build ...
```

## Build Output Organization

### Separation of Concerns

Blade maintains strict separation between build artifacts and source code:

- **Dedicated Output Directories:** Different build configurations generate outputs in separate directories
- **Source Code Protection:** Generated files are isolated from source directories, preventing contamination
- **Configuration Isolation:** Each build option combination maintains independent output space

## Build Artifact Management

### Cleanup Operations

Clear build results (typically unnecessary due to incremental build efficiency):

```bash
blade clean
```

### Key Benefits

- **Incremental Efficiency:** Rarely requires full cleanup operations
- **Space Optimization:** Intelligent dependency tracking minimizes redundant builds
- **Configuration Safety:** Multiple build configurations coexist without interference
- **Developer Productivity:** Reduced build times through selective rebuild strategies
