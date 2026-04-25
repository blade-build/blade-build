# Workspace Configuration

## Workspace Definition

Blade requires projects to have an explicitly defined root directory that serves as the workspace. This workspace forms the foundation for include path resolution in C++ code, requiring `#include` directives to reference files relative to this root directory.

## Workspace Benefits

### Header File Management
- **Name Collision Prevention:** Eliminates header file naming conflicts through absolute path resolution
- **Namespace Organization:** Provides clear hierarchical structure for header file organization
- **Dependency Clarity:** Ensures unambiguous include path resolution across the codebase

### Library Management
- **Library Identification:** Prevents library name conflicts through workspace-based naming
- **Dependency Tracking:** Enables precise dependency resolution and version management
- **Build Optimization:** Reduces ambiguity in library resolution during linking

### Development Efficiency
- **File Discovery:** Simplifies file location through consistent path structures
- **Build Performance:** Optimizes build speed through efficient dependency resolution
- **Team Collaboration:** Standardizes project structure across development environments

## Legacy Project Migration

For projects with existing include path conventions, Blade provides a [migration script](../../tool/fix-include-path.sh) to assist with workspace adoption.

## Workspace Detection Mechanism

### Dynamic Workspace Resolution

Blade employs a dynamic workspace detection strategy rather than relying on configuration files or environment variables. This approach supports developers working with multiple concurrent workspaces.

**Detection Algorithm:**
- **Hierarchical Search:** Blade searches upward from the current directory for a `BLADE_ROOT` file
- **Root Identification:** The directory containing `BLADE_ROOT` becomes the active workspace
- **Universal Access:** Works regardless of current subdirectory depth

### Workspace Creation

Create a workspace by placing a `BLADE_ROOT` file in the root directory:

```console
touch BLADE_ROOT
```

## Workspace Configuration Strategies

### Single Repository Development

For monorepo development models, place `BLADE_ROOT` at the repository root to establish a unified workspace:

```console
$ ls -1
BLADE_ROOT
common/
thirdparty/
xfs/
xcube/
torca/
your_project/
...
```

### Multi-Repository Development

In polyrepo environments, create `BLADE_ROOT` files in each repository to define independent workspaces:

```console
# Repository A
$ ls -1
BLADE_ROOT
src/
libs/

# Repository B  
$ ls -1
BLADE_ROOT
components/
services/
```

## Best Practices

- **Consistent Structure:** Maintain uniform directory organization across workspaces
- **Absolute Paths:** Use workspace-relative paths for all `#include` directives
- **Version Control:** Include `BLADE_ROOT` in version control for team consistency
- **Migration Planning:** Utilize the migration script for legacy project transitions
