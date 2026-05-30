# Java 与 Scala 程序是如何构建的

Java 与 Scala 共享大部分机制：classpath 拼装、JAR 打包（普通、fat、
one-jar）、Maven 坐标解析、测试框架注入，都被收进一个 mixin。每种语言只
需重写真正不同的部分（编译器以及少量构建规则的细枝末节）。

| 文件 | 作用 |
| --- | --- |
| `src/blade/java_targets.py` | `JavaTargetMixIn`、`JavaTarget`、`JavaLibrary`、`JavaBinary`、`JavaTest`、`JavaFatLibrary` |
| `src/blade/scala_targets.py` | `ScalaTarget`、`ScalaLibrary`、`ScalaFatLibrary`、`ScalaTest`（混入该 mixin） |
| `src/blade/backend.py` | `javac` / `scalac` / `javajar` / `fatjar` / `onejar` 规则 |
| `src/blade/config.py` | `java_config` / `java_test_config` / `scala_config` / `scala_test_config` |

## 1. 规则类——组合优于深继承

`JavaTargetMixIn` 集中处理 classpath、JAR 打包、Maven 逻辑，被
`JavaTarget` 与 `ScalaTarget` 同时混入。这样每个规则子类拿到共同行为，
而无需 `Target` 层级里再加共同基类：

- `java_library` / `java_binary` / `java_test` / `java_fat_library`，外
  加 `prebuilt_java_library`（跳过编译，包装给定的 `binary_jar`）。
- `scala_library` / `scala_fat_library` / `scala_test` —— `ScalaTarget`
  允许同一 target 里混入 `.scala` 与 `.java` 源，团队可渐进式引入
  Scala。
- `proto_library` **也**混入 `JavaTargetMixIn`，让下游 Java/Scala 目标
  能直接依赖一个 proto target，按普通 Java dep 一样拿到它的生成 `.jar`。

mixin 避免了菱形继承：每个规则类多继承 `Target`（与 blade 通用集成）
和该 mixin（JVM 特定行为）。

## 2. 编译规则与 classpath 拼装

**javac**（Linux/macOS）—— 规则模板调用用户的 `javac`，带
`-source`/`-target`、`-encoding`、`-classpath ${classpath}`，编译到临时
`${classes_dir}`，再 `jar c[s]f` 打包。Windows 路由到 `javac_compile`
builtin，统一参数转义。

**scalac** —— 直接输出 `.jar`（没有中间 classes 目录），共用同样的
classpath / flag 合成。scalac 调用可以一并接 `.java` 源，与 Java 布局
对齐。

**Classpath 拼装**（`JavaTargetMixIn._get_compile_deps`）走目标的直接
dep、它们的 `exported_deps`、解析后的 Maven 传递依赖。Maven 版本冲突先
解决（`_detect_maven_conflicted_deps`）：直接 `maven_jar` dep 优先，否
则取最高版本。结果去重并排序，让两次相同构建得到位级相同的编译命令。

classpath 分隔符使用 `os.pathsep` —— POSIX 上 `:`，Windows 上 `;` ——
集中一处处理，per-target 代码不必关心。

## 3. JAR 打包形态

- **`.jar`**（`javajar` 规则）：标准形态。若 target 含资源输入，class
  先打成中间 `__classes__.jar`，再与资源合并成最终 `.jar`（保留 Maven
  `src/main/resources` ↔ jar 根映射）。
- **`.fat.jar`**（`fatjar` 规则）：把传递依赖压平到一个归档。打包期再
  做一次冲突检测；`_set_pack_exclusions` 允许按 Maven id 通配符排除
  （如 `org.slf4j:*:*`）。压缩级别在 `java_config` 中可配置。
- **`.one.jar`**（`onejar` 规则）：`java_binary` 形态 —— fat jar 外面套
  一个 boot-loader jar（来自 `java_binary_config.one_jar_boot_jar`），
  自动设置 `Main-Class`，让 `java -jar` 直接可用。

资源处理（`_process_resources` → `_generate_resources`）接受原始文件，
也接受 `location` 引用其它目标产物，省去为生成数据文件单加 `gen_rule`
中转。

## 4. Maven 集成

`maven_jar(name, id, transitive=True/False)` 声明
`group:artifact:version` 坐标。mixin 使用工作区本地的 Maven 缓存
（`.m2/repository/`），按需填充；只读一次 POM 记录传递依赖。blade
**不**在构建时调 `mvn` 解析 —— 它信任记录下来的传递列表，并在其上做自
己的冲突解决。缓存预热后构建可完全离线。

三种 dep 可见性，对应类似 Bazel 的概念：

- `deps`：编译必需，对消费者传递可见。
- `exported_deps`：像 Bazel 的 `exports`；消费者无需重复声明即可访问。
- `provided_deps`：编译期可见，打包时**剔除**（如 war 里的
  servlet-api）。

## 5. 测试框架注入

`java_test` 读 `java_test_config.junit_libs`，通过
`_apply_junit_libs_from_config` 添为隐式 dep。生成的测试启动器默认走
JUnit 的 `JUnitCore`（可由 `main_class` 覆盖），POSIX 上输出 shell
wrapper、Windows 上输出 `.bat` —— 这样可执行体能携带 JaCoCo agent 路径
与覆盖率 flag，省去额外的 `java -jar` 层。若 `junit_libs` 未配置，
blade 会发出清晰的警告指向该配置项，免得用户调一个
`ClassNotFoundException`。

`scala_test` 对称：`scala_test_config.scalatest_libs` 加 `scalatest`
规则。

## 6. 技术细节与用户体验优化

- **没有增量 sjavac。** blade 依赖默认 `javac` 与 ninja 级别的依赖追
  踪，没有用切片的注解处理器。大型重建会重传整个 classpath；超大规模
  Java 单体仓库上这是一个已知开销，值得知悉。
- **Classpath 顺序排序。** Java 运行时不关心，但确定性让生成命令的
  diff 容易读得多。
- **源根推断遵循 Maven 约定。** `_java_sources_paths` 先看
  `src/main/java`、`src/test/java`、`src/java/`，找不到则解析源文件中
  的 `package` 声明。用户可按项目实际布局选择，不必显式 `srcroot`。
- **跨语言 dep 不要钱。** 因为两种语言都产出 JAR、共享同一 mixin，
  `scala_library` 可以依赖 `java_library`，反向亦然，DSL 无特殊语法。
- **Windows 体验。** classpath 分隔符、测试启动脚本扩展名（`.bat`）、
  javac 路径引号都委托给 builtin 工具或 `os.pathsep`。DSL 表层每个 OS
  一致，Linux 上写的 BUILD 通常在 Windows 上直接能用。
- **失败信息。** 编译错误来自 `javac`/`scalac` 原文，但依赖解析/打包失
  败（缺 JAR、版本冲突、找不到 Main-Class）由 `console.diagnose()` 输
  出并带上 BUILD 源位置，不会淹没在 Java 栈轨迹里。
