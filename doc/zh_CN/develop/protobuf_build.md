# `proto_library` 的多语言代码生成机制

`proto_library` 是按语言分发代码生成的入口：同一份 `.proto` 源可以同时
产出 C++ 头/源、Python 模块、Java 源并打成 jar、Go 文件以及 descriptor
set。target 之后**自己以 cc_library 的身份出现**（同时也是 Java、
Python 库）给下游消费，所以 `cc_library` 直接 `deps = [':my_proto']`
即可，不需要中间包装层。

| 文件 | 作用 |
| --- | --- |
| `src/blade/proto_library_target.py` | `ProtoLibrary`（继承 `CcTarget` + `JavaTargetMixIn`） |
| `src/blade/backend.py` | `proto` / `protojava` / `protopython` / `protogo` 规则 |
| `src/blade/config.py` | `proto_library_config`（protoc 路径、插件、well-known protos） |

## 1. 生成什么、怎么控制

一份 proto 文件可能产出多套输出：

- **C++**：`.pb.h` + `.pb.cc`，始终生成。这是核心产物 —— `ProtoLibrary`
  继承 `CcTarget`，把它们直接编进 `cc_library`。
- **Python**：`_pb2.py`，由 target 的 `target_languages` 属性或全局
  `--generate-python` 控制。
- **Java**：`<Class>.java` 加打包 `.jar`，受 `target_languages='java'`
  / `--generate-java` 控制。路径来自 proto 的 `option java_package`。
- **Go**：`.pb.go`，类似机制。输出路径来自 `option go_package`。
- **Descriptor set**：`.descriptors.pb`，按需。

所有输出落到 `build_dir/<pkg>/`。各语言输出通过
`_get_target_file('jar' | 'pylib' | …)` 暴露，下游用与任何其它 target 主
产物相同的 getter 读取。

## 2. 下游集成

三条消费路径，全部通过 proto target 自己的生成元数据：

**C++ 消费者** —— 因为 `ProtoLibrary` 继承 `CcTarget`，下游
`cc_library` 把它列进 `deps` 即可获得：

- `.pb.h` 的路径通过 `declare_hdrs()` / `declare_hdr_dir()` 声明，
  [hdrs check](hdrs_check.md) 因此知道 `pkg/foo.pb.h` 归哪个 target。
- 通过 `export_incs` 暴露 include 路径，`#include "pkg/foo.pb.h"` 无需
  消费者额外加 `-I`。
- 通过 `_transitive_declared_generated_includes()` 实现传递性生成头可
  见性：一个 `#include` 另一个生成头的头文件仍能满足包含检查。
- `.pb.cc` 的 object 直接编入消费者的归档 —— **没有单独的库**可供链
  接；proto 代码生成与编译被合并到一个 target 里。

**Java 消费者** —— mixin 像普通 Java dep 一样暴露 target 的 `.jar`，
proto 代码生成对消费者的 classpath 逻辑透明。

**Python 消费者** —— proto target 的 `.pylib` 列出 `_pb2.py`；
`py_binary` 通过常规 `_get_target_file('pylib')` 遍历拾取。

## 3. protoc 调用

`proto`/`protojava`/`protopython`/`protogo` 规则各自每语言每源文件调一
次 `protoc`。per-language flag 包括 `--proto_path=.`、`-I=<srcdir>`、各
语言输出 flag（`--cpp_out=<build_dir>`、`--python_out=...` 等），以及
从 `proto_library_config.protoc_plugin_config` 解析出的
`--plugin=protoc-gen-<name>` / `--<name>_out=<dir>`。

支持按语言使用不同的 protoc 二进制：`proto_library_config` 留了独立的
`protoc_java` 槽，让 Java 代码生成可以钉到与默认 `protoc` 不同的二进制
或版本。`well_known_protos` 也是按语言声明，原因类似，项目可按输出种
类各钉一份集合而无需 fork 规则定义。

## 4. proto 间的依赖与 include

`import "b.proto";` 仅当**拥有** `b.proto` 的 proto-target 在引用方的
`deps` 里才能正确解析。blade 走 `expanded_deps`，收集每个 dep 的
`public_protos`，作为 implicit 输入交给 `protoc`，所以 `b.proto` 变化
能重建 `a.pb.{h,cc}`（尽管它并不字面在 `a.proto` 的 `srcs` 里）。

C++ 这边，生成的 `a.pb.h` 会 `#include "b.pb.h"`。该 include 由包含栈
机制直接处理：`b.pb.h` 在依赖 proto 的 `declared_genhdrs` 里，通过常规
`_transitive_declared_generated_includes()` 传递可见。用户**不必**为生
成头做额外声明 —— 把依赖 proto 加进 deps 就够了。

## 5. 技术细节与用户体验优化

- **一个 proto target 就是一个 cc_library。** 这是这个子系统最关键的设
  计取舍。其它构建系统有时让你再写
  `cc_proto_library(deps=[':my_proto'])` 作为包装；blade 把两者合并。代
  价是 `ProtoLibrary` 背了不少 mixin；收益是每个 `cc_library` 消费者读
  proto 跟读任何其它 dep 完全一样。
- **`-Ibuild_dir` 免费完成 include 解析。** 因为每个 cc target 的编译
  命令上一直就有 `-Ibuild_dir`（见 [C/C++ 构建](cc_build.md)），
  `#include "pkg/foo.pb.h"` 不需要消费者额外 `-I`。proto target 只需保
  证文件落到 `build_dir/pkg/foo.pb.h`。
- **按语言门控控制 protoc 工作量。** 项目不用 Java 代码就完全不付 Java
  代码生成代价；CLI 上加 `--generate-java` 在某些副构建（如工具）需要
  时翻转全局默认。
- **`.incstk` 与包含检查不知道"这是个 proto 头"。** 生成的 `.pb.h` 和
  任何其它头文件一样；检查通过 `declared_genhdrs` 知道归属。所以新增一
  种 proto 感知语言并不需要新增检查路径。
- **同一工作区里按语言的工具链。** 不同 protoc 二进制（如 C++/Py 用
  `protoc`，Java 用 `protoc_java`）以及按语言独立的插件配置都集中在
  `proto_library_config`，需要混用版本的项目无需 fork 规则定义。
- **跨 target 的生成可见性共享包含声明缓存。** [hdrs check](hdrs_check.md)
  消费的同一个 `inclusion_declaration.data` pickle 列出了所有 proto 的
  生成头，per-target 的检查文件无需再次推导那张表。
