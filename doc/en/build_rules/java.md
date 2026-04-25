# Build Java Targets

## java_library

Build a jar from java source file.

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
        '//common/rpc:rpc_error_code_proto'         # Depends on proto_libraries
        '//common/rpc:rpc_options_proto',
        '//common/net/http/java:http_utilities',    # Depends on other java libraries
        '//thirdparty/java/deps:slf4j',             # Depends on third party java libraries
        '//thirdparty/java/deps:guava',
        '//thirdparty/java/deps:netty-4.0.36.final',
    ]
)
```

- resources attribute

resource file to be packed into this jar,you can also use glob function.
Blade respect the [Maven Standard Directory Layout](https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html),
treats the `resources` dir as the root of resource files to be packed into the generated jar.
So there are some mapping rules, for examples:

resources file path (str or tuple)|path in jar| description
|:----|:----|----|
resources/log4j.properties|log4j.properties | starts after the `resources` dir
src/main/resources/runtime.conf|src/main/resources/runtime.conf | ditto
('src/main/resources/runtime.conf', 'conf/runtime.conf')|conf/runtime.conf | manual rename the packed file
//app/global/countries.xml|app/countries.xml | can't find the root

- prebuilt attribute

Used to describe a prebuilt jar file, but think twice before use it, usually `maven_jar` is more preferable.

```python
java_library(
    name = 'parquet-column-gdt',
    prebuilt = True,
    binary_jar = 'parquet-column-1.9.1-SNAPSHOT.jar',
)
```

- coverage attribute
  bool, Whether generate test coverage data for this library. It is useful to be False in some cases such as srcs are generated.

### Multiple kinds of dependency

For java targets,except the normal `deps`, they also support `exported_deps`,`provided_deps`.
There is a notable difference from C++ targets: for java_library, the dependancies are not **transtive** at the compile phrase.
For example, in this BUILD file:

```python
java_library(name = 'A', srcs = 'A.java', deps = ':B')
java_library(name = 'B', srcs = 'B.java', deps = ':C')
java_library(name = 'C', srcs = 'C.java')
```

The symbols defined in `C.java` is invisible to `A.java`, so when you write the deps for a
java_library, you must add all of the direct dependencies into the deps. you can see you import
list, ensure each library you imported is in the deps list.

- exported_deps attribute

Each dep in the list will be transitive for the user of this library.

As you already know, in the java (and also other JVM languages such as scala) build rules, `deps` are not transitve.
If a type from dependency appears in the public interface of a library, the users may don't know
they should depends one your dependency, use this attribute will be a help.

When a dependency appears in the `exported_deps`, it will be passed to the source file at the compile phrase.

For the above example, if in B.java, some method used the type defined in C.java,the user of `B`,
`A` also have to depends on `C`, or there will be a compile error. if you put `C` int the
`exported_deps` of `B`, `A` will get `C` as as it compile dependency.

```python
java_library(name = 'B', srcs = 'B.java', exported_deps = ':C')
```

- provided_deps attribute

`provided_deps` is used to describe some libraries which will be provied by the runtime environment,
same as the `provided` in maven scope,there dependencies will be used to compile,but they will
not be packed into the final `fatjar`. The scenaio is hadoop or spark. this attribute can reduce
the size of fatjar, and also reduces the conflict with the environment provided libraries.

## maven_jar

Use this rule to describe a jar in the maven repository.

```python
maven_jar (
  name = 'hadoop-common-2.7.2-tdw',
  id = 'org.apache.hadoop:hadoop-common:2.7.2-tdw-1.0.1',  # full maven artifact id
)
```

Besides `name` and `id`, maven_jar also provides the following attributes to fit the use of maven repository.

- classifier attribute
  Specify `classifier`, for the same maven id(group:artifact:version), you can use classifier to locate different jar file.
  Such as hadoop-common-2.2.0.jar and hadoop-common-2.2.0-tests.jar.

- transitive attribute
  Whether use transitive maven dependency, the default value is True, blade will download jar and its
  transitive dependencies; otherwise only the jar file of this target will be downloaded.

In order to avoid duplicated descriptions of artificts with the same id and avoid potential version conflicts,
it is recommended to [centralized management](../config.md#java_config) for `maven_jar`s.

## java_fat_library

Merge all java_library/maven_jar, generate a fatjar, can be used for deploy, same as `jar-with-dependencies` in maven.

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

- exclusions attribute

Specify maven dependencies to be excludes. The syntax is a list of maven ids
(group:artifact:version), also support wildcard, such as:
`com.google.protobuf:protobuf:\*` and `com.google.protobuf:\*:\*`, but only the tail parts can be wildcard.

## java_binary

Build executable from java source files.

```python
java_binary(
    name = 'poppy_java_example',
    srcs = [
        glob('src/com/soso/poppy/tool/*.Java)'
    ],
    deps = [
        '//poppy:poppy_java_client',
        '//poppy:rpc_example_proto',
    ]
)
```

The results include a fat jar with a wrapper shell script.

## java_test

Build and run tests.

```python
java_test(
    name = 'poppy_java_test',
    srcs = [
        glob('test/com/soso/poppy/**/*Test.Java)'
    ],
    deps = [
        '//poppy:poppy_java',
        '//thirdparty/junit:junit',
    ],
)
```
