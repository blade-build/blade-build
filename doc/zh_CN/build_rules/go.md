# 构建 Go 目标

Blade 通过 `go_library`、`go_binary`、`go_test` 构建 Go 程序，另外提供了 `go_package` 便捷包装函数用于自动判断包类型。

## 配置

使用 Go 目标前，需在 `BLADE_ROOT` 中配置 Go 工具链：

```python
go_config(
    go = '/usr/local/go/bin/go',   # 必填
    go_home = '/usr/local/go',     # GOPATH / 构建缓存；可选（留空则用 go 默认值）
)
```

Blade 只支持 **module 模式**：每个目标的包必须位于某个 `go.mod` 之下（其上层最近的
`go.mod` 即为该目标所属模块），不再支持 GOPATH 模式。一个工作区可以包含多个模块；
若模块间存在本地互相 import，请使用 [`go.work`](https://go.dev/ref/mod#workspaces)
或 `replace` 指令，由 `go` 负责解析。

## go_library

将 Go 源码编译为库文件。

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

参数说明：

- `srcs`：Go 源文件。同一目录下的所有 `.go` 文件必须属于同一个 Go 包。
- `deps`：依赖的其他 go_library 或带 Go 输出的 proto_library 目标。
- `extra_goflags`：传递给 Go 编译器的额外参数（`list[str]` 或 `str`）。
- `visibility`：可见性控制。
- `tags`：构建标记。

`go_library` **没有可链接的产物**（Go 的构建缓存取代了 GOPATH 归档）。构建它会对该
包做一次编译检查（`go build`）并生成一个 stamp；使用方依赖它以获得构建顺序与可见性
约束，实际编译仍交给 `go`。`go_library` 是**可选**的——纯 Go、且不跨语言依赖的包无需
Blade 目标，因为使用它的 `go_binary`/`go_test` 在 `go build` 时会自动带上它。

## go_binary

构建 Go 可执行文件。

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

参数与 `go_library` 相同。

`go_binary` 以 **文件模式**（`go build <srcs...>`）从其 `srcs` 构建，而非按整个包构建。
因此，一个目录下若有多个 `main` 文件，可以拆分为各自独立的 `go_binary` 目标——每个程序
一个。

## go_test

构建并运行 Go 测试。

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

额外参数：

- `testdata`：测试数据文件，与其他 test 目标类似。

## go_package

便捷包装函数，自动检测目录类型。

```python
go_package(
    name = 'mypackage',
    deps = [
        '//common/go:base',
    ],
)
```

Blade 会扫描当前目录的 `.go` 文件：

- 如果有文件包含 `package main`，则创建 `go_binary`。
- 否则创建 `go_library`。
- 如果有 `*_test.go` 文件，自动创建 `go_test`。

生成的目标名基于 `name`：`go_binary` / `go_library` 使用 `name`，自动创建的测试名为
`<name>_test`。

## 依赖

go 目标的 `deps` 列出它构建时所需的**其他 Blade 目标**——其他 `go_library`，以及生成
Go 代码的 `proto_library`。Blade 会先构建它们。

在同一个模块内，通常**无需声明 Go→Go 的 `deps`**：`go build` 会从源码自身解析模块内的
import。只有当依赖跨越 Blade 需要排序的语言 / 构建边界时才需要声明——例如
`proto_library`（生成代码）或 `cc_library`（cgo）——或者你希望对它施加可见性 / 依赖
治理时。

引入**第三方包**（如 `github.com/...`）按 Go 的常规方式：在 `go.mod`（多个本地模块时用
`go.work`）中声明，由 Blade 交给 `go` 解析、下载并构建——你**无需**在 Blade `deps`
中列出它们。

## 与 Protobuf 集成

依赖一个 `proto_library` 即可生成并 import Go 的 protobuf 代码：

```python
go_binary(
    name = 'service',
    srcs = ['service.go'],
    deps = [
        '//proto:myproto',  # proto_library 目标
    ],
)
```

`.proto` 中必须把 `option go_package` 设为它的**模块内 import 路径**——即该 `.proto`
所在目录在 Go 模块中的 import 路径：

```protobuf
option go_package = "example.com/mymodule/proto";
```

Blade 把生成的 `.pb.go` 写入**构建目录**（而非源码树），并用 `go build -overlay`
构建使用方的 go 目标——overlay 会在构建期间把这个生成文件映射到它在模块内应有的位置。
源码树保持干净：无需提交任何东西；`.proto` 变化时 `blade build` 会重新生成 `.pb.go`，
并保证在使用它的 go 目标之前完成生成。

由于生成文件只存在于构建目录，它**只对 Blade 的构建可见**：直接 `go build`、`gopls`/IDE
以及模块的外部 importer 都看不到它——这对于**仅在 Blade 构建内部使用**的 Go 代码没有问题。
如果这个包需要**对外发布**（在 Blade 构建之外被 import），请自己生成 `.pb.go`、把它 check in
到 `.proto` 旁边，并按**普通 `go_library`** 构建——这是一个真实的源文件，各种工具和外部
importer 都能正常解析。不要让外部使用方走 overlay 生成的这条路径。

需要 protoc-gen-go 插件——在 `BLADE_ROOT` 中配置
`proto_library_config(protoc_go_plugin=...)`。（`proto_library` 同时也会生成 C++，因此
仍需照常配置 C++ protobuf 工具链。）

## 通过 cgo 使用 C/C++

go 目标可以通过 Go 的 [cgo](https://pkg.go.dev/cmd/cgo) 调用 Blade 的
`cc_library`。在 `deps` 里列出该 `cc_library`，并在 Go 源码中 `import "C"`：

```python
go_binary(
    name = 'app',
    srcs = ['main.go'],
    deps = [
        '//greeter:greeter',  # 一个 cc_library
    ],
)
```

```go
package main

/*
#include "greeter/greeter.h"
*/
import "C"
import "fmt"

func main() { fmt.Println(C.GoString(C.greet())) }
```

Blade 会把这个依赖接入 cgo 构建：cc_library 导出的 include 目录成为 `CGO_CFLAGS`，
它的静态库以及传递依赖的库、系统库成为 `CGO_LDFLAGS`——于是 C 前导块里的 `#include`
能解析、链接器能找到 C 符号。归档会在 go 链接之前先构建好。

说明：

- C 前导块的 include 路径上带有**工作区根目录**和**构建目录**，因此头文件按其相对工作区
  根的路径包含（例如 `#include "greeter/greeter.h"`），与 cc 目标包含头文件的方式一致。
- cgo 只能调用 **C ABI**。C++ 的 `cc_library` 必须暴露 `extern "C"` 入口；Blade 会把
  C++ 运行时（`-lstdc++` / `-lc++`）加到链接中，因此 C++ 归档也能正常链接。
- 只有 `cc_library` 依赖会被链接。`proto_library` 依赖贡献的是它的 **Go**（见 protobuf
  一节），而非它的 C++ 归档。
- 这是唯一支持的方向——go 目标*使用* C/C++。反过来（`cc_binary` 内嵌 Go）是 non-goal：
  每个 Go 归档都自带完整的 Go 运行时，一个进程无法承载两个。
