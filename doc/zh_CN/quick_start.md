# 快速上手

本教程通过一个「Hello World」示例，带你上手 Blade 构建系统。

## 建立工作空间

新建一个工作空间目录：

```console
$ mkdir quick-start
$ cd quick-start
$ touch BLADE_ROOT
```

## 创建 `say` 库

### 头文件定义

创建 `say.h`，内容如下：

```cpp
#pragma once
#include <string>

// 向标准输出输出一条消息
void Say(const std::string& msg);
```

### 实现文件

创建 `say.cpp`：

```cpp
#include "say.h"
#include <iostream>

void Say(const std::string& msg) {
    std::cout << msg << "!\n";
}
```

### BUILD 文件配置

在 `BUILD` 文件中声明该库：

```python
cc_library(
    name = 'say',
    hdrs = ['say.h'],
    srcs = ['say.cpp'],
)
```

**核心概念：**

- `cc_library`：声明一个 C/C++ 库目标
- `hdrs`：对外暴露的头文件
- `srcs`：实现源文件（含私有头文件）

## 创建 `hello` 库

### 头文件定义

创建 `hello.h`：

```cpp
#pragma once
#include <string>

// 生成一条问候消息
void Hello(const std::string& to);
```

### 实现文件

创建 `hello.cpp`：

```cpp
#include "say.h"

void Hello(const std::string& to) {
    Say("Hello, " + to);
}
```

### BUILD 文件配置

在 `BUILD` 文件中追加 `hello` 库：

```python
cc_library(
    name = 'hello',
    hdrs = ['hello.h'],
    srcs = ['hello.cpp'],
    deps = [':say'],
)
```

**依赖管理：**

- `deps`：声明库依赖
- `:` 前缀：表示同一 BUILD 文件内的目标
- 传递依赖：Blade 会自动向上传播依赖关系

## 创建 `hello-world` 可执行程序

### 源文件

创建 `hello-world.c`：

```c
#include "hello.h"

int main() {
    Hello("World");
    return 0;
}
```

### 扩展 BUILD 文件

在 `BUILD` 文件中追加可执行目标：

```python
cc_binary(
    name = 'hello-world',
    srcs = ['hello-world.c'],
    deps = [':hello'],
)
```

**依赖声明策略：**

- `cc_binary`：创建一个可执行目标
- 只声明直接依赖：无需列出传递依赖
- Blade 会自动处理间接依赖

## 构建与运行

### 构建流程

```console
$ blade build :hello-world
Blade(info): Building...
Blade(info): Build success.
```

### 执行程序

```console
$ blade run :hello-world
Blade(info): Building...
Blade(info): Build success.
Blade(info): Run['~/quick-start/build64_release/hello-world']
Hello, World!
```

## 更多示例

想了解覆盖 C/C++、Python、Java、Proto、Thrift 等更多语言特性的完整可运行示例，请参考独立维护的回归测试工作区
[blade-build/blade-test](https://github.com/blade-build/blade-test)。
该仓库 `suites/` 目录下每个子目录都是一个可直接 `blade test //...` 的
示例工程，同时也是 blade 本身的端到端冒烟测试源。

**学习收获：**

- 理解 Blade 的声明式构建配置
- 掌握依赖管理的基本原则
- 学会增量构建的优化思路
- 获得 C/C++ 项目组织的实战经验
