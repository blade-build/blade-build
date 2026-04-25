# 快速上手

让我们从一个 `hello-world` 开始，练习使用 Blade 吧。

## 创建工作空间

```console
$ mkdir quick-start
$ cd quick-start
$ touch BLADE_ROOT
```

## 定义实现 say 库

创建头文件 `say.h`：

```cpp
#pragma once
#include <string>

// Say a message
void Say(const std::string& msg);
```

创建实现文件 `say.cpp`：

```cpp
#include "say.h"
#include <iostream>

void Say(const std::string& msg) {
    std::cout << msg << "!\n";
}
```

创建 `BUILD` 文件，把上述文件描述为一个 `say` 库：

```python
cc_library(
    name = 'say',
    hdrs = ['say.h'],
    srcs = ['say.cpp'],
)
```

`cc_library` 表示这是一个 C/C++ 库，`hdrs` 里表示这个库的对外公开的接口头文件，`srcs` 里的则是其实现文件，
如果有私有头文件，也要放在 `srcs` 里。

## 定义实现 hello 库

创建头文件 `hello.h`：

```cpp
#pragma once
#include <string>

// Say hello to `to`
void Hello(const std::string& to);
```

创建实现文件 `hello.cpp`：

```cpp
#include "say.h"

void Hello(const std::string& to) {
    Say("Hello, " + to);
}
```

创建 `BUILD` 文件，把上述文件描述为一个 `hello` 库：

```python
cc_library(
    name = 'hello',
    hdrs = ['hello.h'],
    srcs = ['hello.cpp'],
    deps = [':say'],
)
```

看起来和 say 库类似，但是多了一个 `deps` 参数，表示依赖 `say` 库。`:` 前缀表示目标在同一个 `BUILD` 文件里。

## 实现 hello-world 程序

创建 `hello-world.cpp` 文件：

```c
#include "hello.h"

int main() {
    Hello("World");
    return 0;
}
```

在 BUILD 文件中增加编译 `hello-world` 的规则调用：

```python
cc_binary(
    name = 'hello-world',
    srcs = ['hello-world.cpp'],
    deps = [':hello'],
)
```

注意规则名是 `cc_binary` 了，`deps` 里需要加入对 `hello` 库的依赖，但是不需要加入对 `say` 库的依赖，因为这是
`hello` 的实现细节，`hello-world` 目标不需要了解，编译和链接时，Blade 会正确处理依赖关系的传递。

构建 `hello-world` 程序：

```console
$ blade build :hello-world
Blade(info): Building...
Blade(info): Build success.
```

运行 `hello-world` 程序：

```console
$ blade run :hello-world
Blade(info): Building...
Blade(info): Build success.
Blade(info): Run '['/data1/code/blade-build/example/quick-start/build64_release/hello-world']'
Hello, World!
```

完整的例子见 [example](../../example) 下的 [quick-start](../../example/quick-start)。
