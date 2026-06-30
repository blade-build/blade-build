# 构建 Go 目标

Blade 通过 `go_library`、`go_binary`、`go_test` 构建 Go 程序，另外提供了 `go_package` 便捷包装函数用于自动判断包类型。

## 配置

使用 Go 目标前，需在 `BLADE_ROOT` 中配置 Go 工具链：

```python
go_config(
    go = '/usr/local/go/bin/go',
    go_home = '/usr/local/go',
)
```

如果启用了 Go modules，设置 `go_module_enabled = True`：

```python
go_config(
    go_home = '/usr/local/go',
    go_module_enabled = True,
    go_module_relpath = '',
)
```

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

输出：`.a` 归档文件，位于 `$go_home/pkg/$GOOS_$GOARCH/`。

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

## 依赖

go 目标的 `deps` 列出它所依赖的**其他 Blade 目标**——`go_library` 目标，以及生成
Go 代码的 `proto_library` 目标。Blade 会先构建它们，并使其可被 import。

如何引入**第三方包**（如 `github.com/...`）取决于 `go_config` 中配置的模式：

- **Go modules**（`go_module_enabled = True`，推荐）：像平常一样在 `go.mod` 中声明
  第三方包。Blade 会在模块目录（`go_module_relpath`）下调用 `go`，由 `go` 负责解析、
  下载并构建这些依赖——你**无需**在 Blade 的 `deps` 中列出它们。
- **GOPATH 模式**（默认）：包从 `$go_home/src/<导入路径>` 解析。把第三方源码放到
  例如 `$go_home/src/github.com/golang/glog` 下，再让 `go` 从 `GOPATH` 中找到它，
  或将其构建为独立的 `go_library` 并加以依赖。

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
