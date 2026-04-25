# Build Scala Targets

## Rules

The `scala_library`, `scala_binary`, `scala_test` are similar to the java rules,
the key difference is that the compiler is changed to scalac, and with the scala runtime.

scala\_test using the [scalatest](https://www.scalatest.org) library.

## Standard Runtime Library

Scala targets always need the standard scala_library, it can be define by maven_jar:

```python
maven_jar(
    name = 'scala_library',
    id = 'org.scala-lang:scala-library:2.12.1',
)
```

It can also be defined by a prebuilt java_library:

```python
java_library(
    name = 'scala_library',
    binary_jar = 'scala-2.12.1/scala-library.jar',
)
```

## interop between java and scala

scala is also a JVM language like java, so scala target can depends on java targets, and vice versa.

But note when java targets depends on a scala library, scala-library should be in the exported_deps
of the scala library, or there will be a waring of something like 'Can't find ScalaSignature.bytes()'.
It should also be a provided_deps to avoid being packed into a scala binary. but for java binary, it
should be list in the final deps, or there will not be a scala runtime when the binary run.

Example:

```python
scala_library(
    name = 'example',
    srcs = 'Example.scala',
    exported_deps = ['//path/to/:scala_library'],
    provided_deps = ['//path/to/:scala_library'],
)
```
