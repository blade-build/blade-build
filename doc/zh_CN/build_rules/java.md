# 构建 Java 目标 #

Blade 早期的开发主要是针对 C/C++/Protobuf 相关的后台服务项目，作为通用的构建系统，也逐步扩展了支持
Java/Python 等的规则。第一版 Java 规则的实现（java_jar_target.py）比较简单，后由于项目需要，参考
Maven/Buck/Bazel 的实现和 Java 语言项目构建习惯和运行场景，重写了新的 Java 构建规则（java_targets.py）

## java_library ##

把 java 源代码编译为库（jar 包）。

```python
java_library(
    name = 'rpc',
    srcs = glob([
        'src/main/java/**/*.java',
    ], exclude = [
        '*Test.java'
    ]),
    resources = [
        'src/main/resources/log4j.properties',
        'resources/rpc.conf',
        'resources/services.xml'
    ],
    deps = [
        '//common/rpc:rpc_error_code_proto',        # 可以依赖proto_library生成的java文件一起编译打包
        '//common/rpc:rpc_options_proto',
        '//poppy:poppy_client',                     # 可以依赖swig_library生成的java文件一起编译打包
        '//common/net/http/java:http_utilities',    # 可以依赖别的 java_library 目标
        '//thirdparty/java/deps:slf4j',             # 依赖第三方包
        '//thirdparty/java/deps:guava',
        '//thirdparty/java/deps:netty-4.0.36.final',
    ]
)
```

- resources 属性

jar 包的资源列表，也可以使用 glob 函数获取一组资源，每个资源文件映射到 jar 包中的路径规则为：

resources 路径（字符串或元组）|jar 包路径
:----|:----
resources/log4j.properties|log4j.properties
src/main/resources/runtime.conf|src/main/resources/runtime.conf
('src/main/resources/runtime.conf', 'conf/runtime.conf')|conf/runtime.conf
//app/global/countries.xml|app/countries.xml

上面表格的最后一行表示非当前目录下的某个资源文件，此外也可以使用目录作为资源，目录会被展开为文件列表，
每一项也遵循上述表格的映射规则。

- prebuilt 属性

主要应用在已经编译打包好的 jar 包，作为一种变通的解决依赖的方式，通常对于外部依赖还是推荐使用 maven_jar 的方式。

```python
java_library(
    name = 'parquet-column-gdt',
    prebuilt = True,
    binary_jar = 'parquet-column-1.9.1-SNAPSHOT.jar',
)
```

- coverage 属性
  bool 类型，是否为本库生成测试覆盖率数据。某些情况，比如 srcs 是生成的代码，可以考虑设置为 False。

### 多种依赖方式 ###

为了适应 java 项目的需要，除了原有的 deps 依赖，新增了 exported_deps/provided_deps 依赖，这里首先
需要强调的是 java_library 进行编译生成 class（jar 包）的时候**依赖不传递**，即如下 BUILD 文件中的
C.java 中定义的符号对 A.java 不可见，即在写 java_library 的 deps 时，应按需添加，与源文件中的
import 能够对应起来：deps what you imports。

```python
java_library(name = 'A', srcs = 'A.java', deps = ':B')
java_library(name = 'B', srcs = 'B.java', deps = ':C')
java_library(name = 'C', srcs = 'C.java')
```

- exported_deps 属性

和 C++不同，Java（以及 scala 等 JVM 上的语言）的构建规则中，deps 里描述的库只提供给编译当前库的源代码时使用，不会自动透传给库的使用者。
如果库所依赖的类型出现在类的公有方法时，如果被依赖的库只出现在 deps 中，由于不会被透传给其使用者，就会因找不到符号而导致编译失败，需要使用 exported_deps 属性。

出现在 exported_deps 属性中的库，编译阶段会被透传给其使用者。

比如上述例子中的 B.java，如果在其某个方法的参数中引入了 C.java 定义的符号，会导致依赖 B 的
java_library 也不得不依赖 C，否则编译报错，这个时候可以将 C 作为 B 的导出依赖（exported_deps），
这样依赖 B 的目标会自动传递依赖到 C。

```python
java_library(name = 'B', srcs = 'B.java', exported_deps = ':C')
```

- provided_deps 属性

provided_deps 用于表示那些运行环境提供的依赖，类似 maven scope 中的 provided，这些依赖用于当前
java_library 的编译，但是当这个 java_library 直接或者间接被 java_fat_library 依赖时，provided deps
不会被打包到 fatjar 中，应用场景比如集群环境的依赖（hadoop，spark 等），可以有效减小 fatjar 的文件大小，并减少和运行环境已经提供的库冲突的风险。

## maven_jar ##

从 maven 仓库获取第三方发布包（release/snapshot），这里的第三方是相对的概念，泛指本项目（java_library）的外部依赖。

```python
maven_jar (
  name = 'hadoop-common-2.7.2-tdw',
  id = 'org.apache.hadoop:hadoop-common:2.7.2-tdw-1.0.1',  # 完整的maven artifact id
)
```

除了 name 和 id 属性，maven_jar 也提供了如下属性，兼容 maven 仓库中选取依赖的多种方式。

- classifier 属性
  指定 classifier 值，对于同一组 id（group:artifact:version），可以用 classifier 来指定不同的 jar 包，
  如 hadoop-common-2.2.0.jar 和 hadoop-common-2.2.0-tests.jar。
- transitive 属性
  指定是否传递，默认是 True，下载 jar 包及其传递依赖，指定为 False 时表示只下载 id 对应的 standalone
  jar 包，不下载依赖，用于解决某些运行时依赖下载传递依赖时的失败。

为了避免对同一个 id 的制品重复描述以及避免潜在的版本冲突，建议对 maven_jar 进行[集中管理](../config.md#java_config)。

## java_fat_library ##

聚合所有依赖的 java_library/maven_jar，生成一个 fatjar 用于部署，类似 maven 的 jar-with-dependencies 功能。

```python
java_library(
    name = 'log_process',
    srcs = glob(['**/*.java'], exclude = ['*Test.java']),
    resources = glob(['resources/*']),
    deps = [
        ':log_proto',
        '//log/com/tencent/monitor:monitor',
        '//log/com/tencent/monitor:schema',
        '//thirdparty/java/deps:hbase-client',
        '//thirdparty/java/deps:snappy',
    ],
    provided_deps = [
        '//thirdparty/java/deps:hadoop-common',
        '//thirdparty/java/deps:hadoop-mapreduce',
        '//thirdparty/java/deps:log4j',
        '//thirdparty/java/deps:slf4j',
    ],
)

java_fat_library(
    name = 'log_process_main',
    deps = [
        ':log_process',
        '//thirdparty/java/deps:guava',
    ],
    resources = [
        ('//log/configuration/log4j.properties', 'log4j.properties'),
        ('//log/configuration/sites.xml', 'conf/sites.xml'),
    ],
    exclusions = [
        'com.google.protobuf:*:*',
        'org.apache.spark:*:*',
    ]
)

```

- name/srcs/deps/resources 和 java_library 相同

- exclusions 属性

指定需要排除的 maven 依赖，形式为 maven id（group:artifact:version），支持通配符形式，
如 com.google.protobuf:protobuf:\* 和 com.google.protobuf:\*:\*。

## java_binary ##

把 java 源代码编译为可执行文件

```python
java_binary(
    name = 'poppy_java_example',
    srcs = [
        glob('src/com/soso/poppy/tool/*.java')
    ],
    deps = [
        '//poppy:poppy_java_client',
        '//poppy:rpc_example_proto',
    ]
)
```

编译结果包括一个启动用的 shell 脚本文件和一个已经包含了相关依赖的 fat-jar。

## java_test ##

编译和运行 java 测试代码。

```python
java_test(
    name = 'poppy_java_test',
    srcs = [
        glob('test/com/soso/poppy/**/*Test.java')
    ],
    deps = [
        '//poppy:poppy_java',
        '//thirdparty/junit:junit',
    ],
)
```
