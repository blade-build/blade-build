# Quick Start Guide

This tutorial demonstrates Blade usage through a "Hello World" example, providing hands-on experience with the build system.

## Workspace Setup

Create a new workspace directory:

```console
$ mkdir quick-start
$ cd quick-start
$ touch BLADE_ROOT
```

## Creating the `say` Library

### Header File Definition

Create `say.h` with the following content:

```cpp
#pragma once
#include <string>

// Output a message to standard output
void Say(const std::string& msg);
```

### Implementation File

Create `say.cpp` with the implementation:

```cpp
#include "say.h"
#include <iostream>

void Say(const std::string& msg) {
    std::cout << msg << "!\n";
}
```

### BUILD File Configuration

Define the library in a `BUILD` file:

```python
cc_library(
    name = 'say',
    hdrs = ['say.h'],
    srcs = ['say.cpp'],
)
```

**Key Concepts:**
- `cc_library`: Declares a C/C++ library target
- `hdrs`: Public interface header files
- `srcs`: Implementation source files (including private headers)

## Creating the `hello` Library

### Header File Definition

Create `hello.h`:

```cpp
#pragma once
#include <string>

// Generate a greeting message
void Hello(const std::string& to);
```

### Implementation File

Create `hello.cpp`:

```cpp
#include "say.h"

void Hello(const std::string& to) {
    Say("Hello, " + to);
}
```

### BUILD File Configuration

Extend the `BUILD` file with the `hello` library:

```python
cc_library(
    name = 'hello',
    hdrs = ['hello.h'],
    srcs = ['hello.cpp'],
    deps = [':say'],
)
```

**Dependency Management:**
- `deps`: Specifies library dependencies
- `:` prefix: Indicates target within the same BUILD file
- Transitive dependencies: Blade automatically handles dependency propagation

## Creating the `hello-world` Executable

### Source File

Create `hello-world.c`:

```c
#include "hello.h"

int main() {
    Hello("World");
    return 0;
}
```

### BUILD File Extension

Add the executable target to the `BUILD` file:

```python
cc_binary(
    name = 'hello-world',
    srcs = ['hello-world.c'],
    deps = [':hello'],
)
```

**Dependency Strategy:**
- `cc_binary`: Creates an executable target
- Direct dependencies only: Only specify immediate dependencies
- Transitive handling: Blade automatically includes indirect dependencies

## Build and Execution

### Build Process

```console
$ blade build :hello-world
Blade(info): Building...
Blade(info): Build success.
```

### Program Execution

```console
$ blade run :hello-world
Blade(info): Building...
Blade(info): Build success.
Blade(info): Run['~/quick-start/build64_release/hello-world']
Hello, World!
```

## More Examples

For complete, runnable examples covering C/C++, Python, Java, Proto, Thrift
and other language features, see the dedicated regression workspace
[blade-build/blade-test](https://github.com/blade-build/blade-test). Each
subdirectory under `suites/` is a standalone project that you can build and
test with `blade test //...`, and also serves as the end-to-end smoke test
source for blade itself.

**Learning Outcomes:**
- Understanding Blade's declarative build configuration
- Mastering dependency management principles
- Learning incremental build optimization strategies
- Gaining practical experience with C/C++ project structure
