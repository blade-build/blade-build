# 构建 Python 目标

## py_library

把 py 源代码编译为库。

```python
py_library(
    name = 'protobuf_util',
    srcs = [
        'protobuf_util.py'
    ],
    deps = [
        ':common',               # 可以依赖别的python库
    ]
)
```

当在代码中 import python 模块时，需要从 workspace 目录开始写起。可以通过 base 属性来改变这个行为，比如：

```python
base = '.'
```

把模块的根路径改为当前 BUILD 文件所在的目录。

py_library 还支持

* prebuilt=True
  主要应用于 zip 格式的包。

示例：

```python
python_library(
    name = 'protobuf-python',
    prebuilt = True,
    srcs = 'protobuf-python-3.4.1.egg',
)
```

srcs 是 python 包的文件名，只能有一个文件，支持 whl 和 egg 两种格式

## py_binary

把 py 源代码编译为可执行文件。

```python
py_binary(
    name = 'example',
    srcs = [
        'example.py'
    ],
    deps = [
        '//python:common',
    ]
)
```

当 srcs 多于一个时，需要用 main 属性指定入口文件。

python_binary 也支持 base 属性

编译出来的可执行文件以及打包了所有的依赖，可以直接执行。可以用 `unzip -l` 查看其中包含的文件。

属性：

* exclusions: list(str)
  打包进可执行文件的文件时，要排除的路径的模式列表，注意路径是打包后的路径，可以通过 `unzip -l` 查看，示例：

  ```python
  exclusions = ['google/protobuf/*'],
  ```

## py_test

编译和运行 python 测试代码。

```python
py_test(
    name = 'common_test',
    srcs = [
        'common_test.py'
    ],
    deps = [
        ':common',
    ],
    testdata = [...],
)
```

我们一般使用 unittest 库进行 python 单元测试。

## 使用 protobuf

proto 文件首先需要用[proto_library](idl.md#proto_library)来描述，在 py_* 的 deps 中引入。
blade build 时会自动生成相应的 python protobuf 编码解码库。

在 python 代码中的 import 路径规则是，从 workspace 根出发，/替换为.，文件名结尾的.proto 替换为_pb2，比如：

```python
# proto文件路径为 //common/base/user_info.proto
import common.base.user_info_pb2
```
