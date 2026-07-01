# Build Go Targets

Blade uses `go_library`, `go_binary`, and `go_test` to build Go packages.
There is also a `go_package` convenience wrapper that auto-detects the package type.

## Configuration

Before using go targets, configure the Go toolchain in `BLADE_ROOT`:

```python
go_config(
    go = '/usr/local/go/bin/go',   # required
    go_home = '/usr/local/go',     # GOPATH / build cache; optional (empty = go default)
)
```

Blade builds Go in **module mode only**: each target's package must sit under a
`go.mod` (the nearest one at or above the target's directory is its module).
GOPATH-mode projects are not supported. A workspace may contain multiple modules;
for local cross-module imports use a [`go.work`](https://go.dev/ref/mod#workspaces)
file or `replace` directives, which `go` resolves.

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

A `go_library` has **no linkable artifact** (the Go build cache replaced the
GOPATH archive). Building one compile-checks the package (`go build`) and emits a
stamp; consumers depend on it for ordering and visibility and let `go` recompile
the package. A `go_library` is optional — a pure-Go package with no cross-language
dependency needs no Blade target, since `go build` of a consuming `go_binary`/
`go_test` pulls it in.

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

A `go_binary` is built from its `srcs` in **file mode** (`go build <srcs...>`), not
by whole package. This means a single directory holding several `main` files can
be split into separate `go_binary` targets — one per program.

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

The generated targets are named after `name`: the `go_binary`/`go_library` takes
`name`, and the auto-created test is `<name>_test`.

## Dependencies

A go target's `deps` lists **other Blade targets** it must be built with — other
`go_library` targets and `proto_library` targets that emit Go code. Blade builds
those first.

Within one module you generally **don't need to declare Go→Go `deps`**: `go build`
resolves intra-module imports from the source itself. Declare a dep when it
crosses a language/build boundary Blade must order — a `proto_library` (generated
code) or a `cc_library` (cgo) — or when you want visibility / dependency
governance on it.

Pull in **third-party packages** (e.g. `github.com/...`) the normal Go way:
declare them in `go.mod` (or a `go.work` for multiple local modules). Blade
delegates to `go`, which resolves, downloads, and builds them — you do **not**
list them in Blade `deps`.

## Using Protobuf with Go

Depend on a `proto_library` to generate and import Go protobuf code:

```python
go_binary(
    name = 'service',
    srcs = ['service.go'],
    deps = [
        '//proto:myproto',  # proto_library target
    ],
)
```

The `.proto` must set `option go_package` to its **in-module import path** — the
import path of the `.proto`'s own directory within the Go module:

```protobuf
option go_package = "example.com/mymodule/proto";
```

Blade generates the `.pb.go` **into the build directory** — not the source tree —
and builds consuming go targets with `go build -overlay`, which maps the generated
file into its in-module location just for the build. The source tree stays clean:
nothing to commit, and `blade build` regenerates the `.pb.go` when the `.proto`
changes, ordered before the consuming go target.

Because the generated file lives only in the build directory, it is visible **only
to Blade's build**. A plain `go build`, `gopls`/IDEs, and external importers of your
module do not see it — which is fine for Go that is internal to your Blade build.
For a package you **publish** (imported outside your Blade build), generate the
`.pb.go` yourself, check it in beside the `.proto`, and build it as an ordinary
`go_library` — a real source file that tooling and external importers resolve
normally. Don't route external consumers through the overlay-generated Go.

Requires the protoc-gen-go plugin — `proto_library_config(protoc_go_plugin=...)`
in `BLADE_ROOT`. (`proto_library` also emits C++, so the C++ protobuf toolchain
must be configured as usual.)
