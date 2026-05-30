# How `proto_library` handles multi-language codegen

A `proto_library` is the entry point to a small per-language codegen
fan-out: one `.proto` source can become C++ headers/sources, Python
modules, Java sources packaged into a jar, Go files, and a descriptor
set, all in the same build. The target then **presents itself as a
cc_library** (and as a Java library, and as a Python library) to
downstream consumers, so a `cc_library` can `deps = [':my_proto']`
without an intermediate layer.

| File | Role |
| --- | --- |
| `src/blade/proto_library_target.py` | `ProtoLibrary` (inherits `CcTarget` + `JavaTargetMixIn`) |
| `src/blade/backend.py` | `proto` / `protojava` / `protopython` / `protogo` rule emission |
| `src/blade/config.py` | `proto_library_config` (protoc paths, plugins, well-known protos) |

## 1. What gets generated, and how it's controlled

A single proto file potentially produces multiple output sets:

- **C++**: `.pb.h` + `.pb.cc`, always generated. These are the central
  artifact — `ProtoLibrary` inherits from `CcTarget` and compiles them
  into a real `cc_library` output.
- **Python**: `_pb2.py` files, gated by the target's `target_languages`
  attribute or the global `--generate-python` flag.
- **Java**: `<Class>.java` files plus a packaged `.jar`, gated by
  `target_languages='java'` / `--generate-java`. Path comes from the
  proto's `option java_package`.
- **Go**: `.pb.go`, gated similarly. Output path from `option go_package`.
- **Descriptor set**: `.descriptors.pb` for tooling, on request.

All outputs land in `build_dir/<pkg>/`. Per-language outputs are exposed
as `_get_target_file('jar' | 'pylib' | ...)` so downstream rules read
them with the same getter as any other target's primary output.

## 2. Downstream integration

Three different consumer paths, all wired through the proto target's own
generated metadata:

**C++ consumers** — because `ProtoLibrary` extends `CcTarget`, a
downstream `cc_library` lists it in `deps` and gets:

- The `.pb.h` paths declared via `declare_hdrs()` / `declare_hdr_dir()`,
  so the [hdrs check](hdrs_check.md) knows which target owns
  `pkg/foo.pb.h`.
- Include paths via `export_incs`, so `#include "pkg/foo.pb.h"`
  resolves without the consumer having to add `-I` lines.
- Transitive generated-header visibility through
  `_transitive_declared_generated_includes()`, so a header that
  `#include`s another generated header still satisfies the inclusion
  check.
- The `.pb.cc` objects linked into the consumer's archive — there is no
  separate library to link; proto code generation and compilation are
  fused into one target.

**Java consumers** — the mixin exposes the target's `.jar` like any
other Java dep; the proto code generation is invisible to the consumer's
classpath logic.

**Python consumers** — the proto target's `.pylib` lists its
`_pb2.py` files; `py_binary` picks them up through the normal
`_get_target_file('pylib')` walk.

## 3. protoc invocation

The `proto`/`protojava`/`protopython`/`protogo` ninja rules each call
`protoc` once per source file per language. Per-language flags include
`--proto_path=.`, `-I=<srcdir>`, the per-language output flag
(`--cpp_out=<build_dir>`, `--python_out=...`, etc.), and any
`--plugin=protoc-gen-<name>` / `--<name>_out=<dir>` resolved from
`proto_library_config.protoc_plugin_config`.

Per-language protoc binaries are supported: `proto_library_config` has a
separate `protoc_java` slot, so Java codegen can be pinned to a different
binary or version than the default `protoc`. `well_known_protos` is also
declared per language for the same kind of reason, so a project can pin a
different set per output kind without forking the rule definitions.

## 4. Inter-proto deps and includes

`import "b.proto";` is only resolved correctly if the proto-target that
owns `b.proto` is in the importing target's `deps`. blade walks
`expanded_deps`, collects each dep's `public_protos`, and passes them as
implicit inputs to `protoc` so changes to `b.proto` rebuild the
generated `a.pb.{h,cc}` even though they aren't textually in `a.proto`'s
`srcs`.

For C++, the generated `a.pb.h` `#include`s `b.pb.h`. That include is
**directly** taken care of by the inclusion-stack mechanism: `b.pb.h` is
in the dep proto's `declared_genhdrs`, transitively visible through the
normal `_transitive_declared_generated_includes()` walk. Users do not
have to declare anything special about generated headers — being on the
deps edge to the dep proto is enough.

## 5. Implementation details and UX optimizations

- **A proto target *is* a cc_library.** This is the most important
  design decision in this subsystem. Other build systems sometimes have
  you write `cc_proto_library(deps=[':my_proto'])` as a separate
  wrapper; blade collapses the two into one target. The cost is that
  `ProtoLibrary` carries a lot of mixin baggage; the benefit is that
  every `cc_library` consumer reads identical from any other dep.
- **`-Ibuild_dir` does the include resolution work for free.** Because
  every cc target already has `-Ibuild_dir` on its compile line (see
  [C/C++ build](cc_build.md)), `#include "pkg/foo.pb.h"` resolves
  without extra `-I` lines per consumer. proto targets only have to
  guarantee the file lands at `build_dir/pkg/foo.pb.h`.
- **Per-language gating keeps protoc work in check.** A project that
  doesn't use Java code from its protos pays no cost for Java codegen.
  Adding `--generate-java` at the CLI flips the global default if a
  side build (e.g. for tooling) needs it.
- **The `.incstk` + inclusion check are oblivious to "this is a proto
  header".** Generated `.pb.h` files are headers like any other; the
  check uses `declared_genhdrs` to know who owns them. So adding a new
  proto-aware language doesn't require a new check pathway.
- **Per-language toolchains in one workspace.** Distinct protoc binaries
  (e.g. `protoc` for C++/Python, `protoc_java` for Java) and per-language
  plugin configs are all declared in one place — `proto_library_config`
  — so a project that needs to mix versions doesn't have to fork the
  rule definitions.
- **Cross-target generated visibility shares the inclusion-declaration
  cache.** The same `inclusion_declaration.data` pickle that
  [the hdrs check](hdrs_check.md) consumes lists every proto's
  generated headers, so the per-target check files don't have to
  re-derive that map.
