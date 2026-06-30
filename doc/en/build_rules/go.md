# Build Go Targets

Blade uses `go_library`, `go_binary`, and `go_test` to build Go packages.
There is also a `go_package` convenience wrapper that auto-detects the package type.

## Configuration

Before using go targets, configure the Go toolchain in `BLADE_ROOT`:

```python
go_config(
    go = '/usr/local/go/bin/go',
    go_home = '/usr/local/go',
)
```

When Go modules are enabled, set `go_module_enabled = True`:

```python
go_config(
    go_home = '/usr/local/go',
    go_module_enabled = True,
    go_module_relpath = '',
)
```

## go_library

Build a Go package as a library.

```python
go_library(
    name = 'mylib',
    srcs = [
        'mylib.go',
        'helper.go',
    ],
    deps = [
        '//common/go:base',
    ],
)
```

Attributes:

- `srcs`: Go source files. All `.go` files in the same directory must belong to the same Go package.
- `deps`: Other go_library or proto_library targets with Go output.
- `extra_goflags`: Extra flags passed to the Go compiler (`list[str]` or `str`).
- `visibility`: Visibility specification.
- `tags`: Build tags.

Output: a `.a` archive file placed under `$go_home/pkg/$GOOS_$GOARCH/`.

## go_binary

Build a Go executable.

```python
go_binary(
    name = 'myserver',
    srcs = [
        'main.go',
    ],
    deps = [
        ':mylib',
    ],
)
```

Attributes are the same as `go_library`.

## go_test

Build and run a Go test binary.

```python
go_test(
    name = 'mylib_test',
    srcs = [
        'mylib_test.go',
    ],
    deps = [
        ':mylib',
    ],
    testdata = [
        'testdata/config.json',
    ],
)
```

Additional attributes:

- `testdata`: Test data files, similar to other test targets.

## go_package

Convenience wrapper that automatically detects whether a directory contains a library or a command.

```python
go_package(
    name = 'mypackage',
    deps = [
        '//common/go:base',
    ],
)
```

Blade scans the current directory for `.go` files:

- If any file has `package main`, a `go_binary` is created.
- Otherwise, a `go_library` is created.
- If `*_test.go` files exist, a `go_test` is created automatically.

## Dependencies

A go target's `deps` lists **other Blade targets** it depends on — `go_library`
targets and `proto_library` targets that emit Go code. Blade builds those first
and makes them importable.

How you pull in **third-party packages** (e.g. `github.com/...`) depends on the
mode configured in `go_config`:

- **Go modules** (`go_module_enabled = True`, recommended): declare third-party
  packages in your `go.mod` as usual. Blade invokes `go` inside the module
  directory (`go_module_relpath`), so `go` resolves, downloads, and builds those
  dependencies — you do **not** list them in Blade `deps`.
- **GOPATH mode** (the default): packages are resolved from
  `$go_home/src/<import-path>`. Place the third-party source under, for example,
  `$go_home/src/github.com/golang/glog`, then either let `go` pick it up from
  `GOPATH` or build it as its own `go_library` and depend on that target.

## Using Protobuf with Go

Add a `proto_library` dependency to generate Go protobuf code:

```python
go_library(
    name = 'service',
    srcs = ['service.go'],
    deps = [
        '//proto:myproto',  # proto_library target
    ],
)
```

The proto file must contain a `go_package` option:

```protobuf
option go_package = "github.com/example/myproto";
```
