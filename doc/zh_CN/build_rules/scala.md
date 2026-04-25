# 构建 Scala 目标 #

## 规则 ##

scala_library scala_binary scala_test 用法类似 java，区别是编译器换成了 scalac。
scala\_test 使用 [scalatest](https://www.scalatest.org) 库。

## 标准库 ##

构建 Scala 目标总是离不开 scala 标准库，可以通过 maven_jar 来定义：

```python
maven_jar(
    name = 'scala_library',
    id = 'org.scala-lang:scala-library:2.12.1',
)
```

也可以通过 prebuilt 的 java_library 来定义：

```python
java_library(
    name = 'scala_library',
    binary_jar = 'scala-2.12.1/scala-library.jar',
)
```

## java 和 scala 互操作 ##

和 java 一样，scala 也是 JVM 上的语言，因此 scala 目标也可以依赖 java 库，反之亦然。

不过需要注意，java 构建目标可以依赖 scala 库时，scala 目标中应该把 scala-library 纳入 exported_deps。
否则编译时 javac 会发出找不到 ScalaSignature.bytes() 符号的警告。
但是它也应该同时出现在 provided_deps 里，否则它就会被打包进 scala binary 里，和 scala 环境已经提供的冲突。
但是对于 java_binary，则又需要显式地依赖 scala-library。

```python
scala_library(
    name = 'example',
    srcs = 'Example.scala',
    exported_deps = ['//path/to/:scala_library'],
    provided_deps = ['//path/to/:scala_library'],
)
```
