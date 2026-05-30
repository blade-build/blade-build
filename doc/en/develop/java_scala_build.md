# How Java and Scala programs are built

Java and Scala share most of their machinery: classpath assembly, JAR
packaging (plain, fat, one-jar), Maven coordinate resolution, and test
framework injection all live behind a single mixin so each language can
override only the parts that are genuinely different (the compiler and a
few build-rule plumbing details).

| File | Role |
| --- | --- |
| `src/blade/java_targets.py` | `JavaTargetMixIn`, `JavaTarget`, `JavaLibrary`, `JavaBinary`, `JavaTest`, `JavaFatLibrary` |
| `src/blade/scala_targets.py` | `ScalaTarget`, `ScalaLibrary`, `ScalaFatLibrary`, `ScalaTest` (inherit the mixin) |
| `src/blade/backend.py` | `javac` / `scalac` / `javajar` / `fatjar` / `onejar` rule emission |
| `src/blade/config.py` | `java_config` / `java_test_config` / `scala_config` / `scala_test_config` |

## 1. Rule classes — composition over a deep hierarchy

`JavaTargetMixIn` centralizes classpath/jar-packing/Maven logic and is
mixed in by both `JavaTarget` and `ScalaTarget`. Each rule subclass picks
up the shared behavior without forcing a single common base in `Target`'s
hierarchy:

- `java_library` / `java_binary` / `java_test` / `java_fat_library`,
  plus `prebuilt_java_library` (skips compilation, wraps a supplied
  `binary_jar`).
- `scala_library` / `scala_fat_library` / `scala_test` — `ScalaTarget`
  accepts both `.scala` and `.java` sources in a single target, so a
  team can adopt Scala incrementally.
- `proto_library` *also* mixes in `JavaTargetMixIn`, so a downstream
  Java/Scala target can depend directly on a proto target and pick up
  its generated `.jar` exactly like any other Java dep.

The mixin avoids a diamond: each rule class multiply-inherits from
`Target` (for general blade integration) and from the mixin (for
JVM-specific behavior).

## 2. Compile rules and classpath assembly

**javac** (Linux/macOS) — the rule template runs the user's `javac` with
`-source`/`-target`, `-encoding`, `-classpath ${classpath}`, into a temp
`${classes_dir}`, then `jar c[s]f` to pack. On Windows it routes through
a `javac_compile` builtin to keep argument quoting consistent.

**scalac** — emits the `.jar` directly (no intermediate classes dir),
sharing the same classpath/flag composition. Scala compiles can include
`.java` sources in the same call, so the layout matches Java's.

**Classpath assembly** (`JavaTargetMixIn._get_compile_deps`) walks the
target's direct deps, their `exported_deps`, and the resolved Maven
transitive deps. Maven version conflicts are resolved up-front
(`_detect_maven_conflicted_deps`): a direct `maven_jar` dep wins, otherwise
the highest version wins. Result is deduplicated and sorted, so two
identical builds get bit-identical compile commands.

The classpath separator is `os.pathsep` — `:` on POSIX, `;` on Windows —
done in one place so per-target code doesn't have to think about it.

## 3. JAR packaging shapes

- **`.jar`** (`javajar` rule): the standard form. If the target has
  resource inputs, classes are packed into an intermediate
  `__classes__.jar` first, then merged with resources into the final
  `.jar` (preserves Maven's `src/main/resources` ↔ jar-root mapping).
- **`.fat.jar`** (`fatjar` rule): flattens transitive deps into one
  archive. Conflict detection runs at packaging time as well as compile
  time; `_set_pack_exclusions` lets the user filter by Maven-id wildcard
  (e.g. `org.slf4j:*:*`). Compression level is configurable in
  `java_config`.
- **`.one.jar`** (`onejar` rule): the `java_binary` form — a fat jar
  wrapped with a boot-loader jar (from `java_binary_config.one_jar_boot_jar`)
  that sets `Main-Class` so `java -jar` works.

Resource handling (`_process_resources` → `_generate_resources`) accepts
both raw files and `location` references to other targets' outputs, so
generated data files can be packaged without an intermediate `gen_rule`
shuffle.

## 4. Maven integration

`maven_jar(name, id, transitive=True/False)` declares a `group:artifact:version`
coordinate. The mixin uses a workspace-local Maven cache
(`.m2/repository/`), populated on demand, and reads the artifact's POM
once to record its transitive deps. Blade does **not** invoke `mvn` for
resolution at build time — it trusts the recorded transitive list,
applying its own conflict resolution on top. This keeps the build offline
once the cache is warm.

Three dep visibilities mirror what Bazel-like systems give you:

- `deps` — required to compile, transitively visible to consumers.
- `exported_deps` — like `exports` in Bazel; reachable by consumers
  without re-declaring.
- `provided_deps` — visible at compile time, **subtracted** at packaging
  (e.g. servlet-api in a war).

## 5. Test framework injection

`java_test` reads `java_test_config.junit_libs` and adds them as
implicit deps via `_apply_junit_libs_from_config`. The generated test
launcher defaults to JUnit's `JUnitCore` runner (overridable via
`main_class`) and is emitted as a shell wrapper on POSIX / `.bat` on
Windows — that way the test executable can carry JaCoCo agent paths and
coverage flags without an extra `java -jar` layer. If `junit_libs` is
unset, blade emits a clear warning pointing users at the config item
rather than letting them debug a `ClassNotFoundException`.

`scala_test` is symmetric: `scala_test_config.scalatest_libs` plus a
`scalatest` rule.

## 6. Implementation details and UX optimizations

- **No incremental sjavac.** Blade relies on the default `javac` and on
  ninja-level dep tracking, not on a partitioned annotation processor.
  Large rebuilds re-pass the full classpath; for very large Java
  monorepos that's a known overhead worth being aware of.
- **Classpath order is sorted.** Java's runtime doesn't care, but
  determinism makes diffs of generated build commands much easier to
  read.
- **Source-root inference is Maven-aware.** `_java_sources_paths` checks
  conventional Maven paths (`src/main/java`, `src/test/java`,
  `src/java/`) first and falls back to parsing the `package` declaration
  from a source. So users can pick the layout that suits the project
  without an explicit `srcroot` attribute.
- **Cross-language deps are free.** Because both languages emit JARs and
  share the same mixin, a `scala_library` can depend on a `java_library`
  and vice versa with no special syntax.
- **Windows ergonomics.** Classpath separator, test-launcher script
  extension (`.bat`), and javac path-quoting are all delegated to the
  builtin tool or `os.pathsep`. The DSL surface stays the same on every
  OS, so a BUILD file written on Linux usually just works on Windows.
- **Failure messages.** Compile errors come straight from `javac`/`scalac`,
  but the dep-resolution and packaging failures (missing JAR, version
  conflict, missing main class) are surfaced through `console.diagnose()`
  with the BUILD source location, so they don't get lost in a wall of
  Java stack traces.
