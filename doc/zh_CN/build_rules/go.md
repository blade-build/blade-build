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

在 deps 中添加 `proto_library` 即可自动生成 Go protobuf 代码：

```python
go_library(
    name = 'service',
    srcs = ['service.go'],
    deps = [
        '//proto:myproto',  # proto_library 目标
    ],
)
```

proto 文件中需要指定 `go_package` 选项：

```protobuf
option go_package = "github.com/example/myproto";
```
