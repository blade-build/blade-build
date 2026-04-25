# Build Python Targets

## py_library

Build a python library from source code

```python
py_library(
    name = 'protobuf_util',
    srcs = [
        'protobuf_util.py'
    ],
    deps = [
        ':common',               # Depends on other python library
    ]
)
```

When importing the python module in your code, you need to start writing from the workspace directory.
This behavior can be changed through the base attribute, for example:

```python
base = '.'
```

Change the root path of the module to the directory where the current BUILD file is located.

py_library also supports

* prebuilt=True
  Mainly used in the zip package.

Example:

```python
python_library(
    name = 'protobuf-python',
    prebuilt = True,
    srcs = 'protobuf-python-3.4.1.egg',
)
```

`srcs` is the file name of the python package, there can only be one file, and it supports both `whl` and `egg` formats.

## py_binary

Compile the py source code into an executable file.

Example:

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

When there are more than one `srcs`, you need to specify the entry file with the `main` attribute.

python_binary also support the `base` attribute.

The generated executable file contains all dependencies and can be executed directly. You can use `unzip -l` to view the file content.

Attributes:

* exclusions: list(str)
  When packaging the file into the executable file, the pattern list of the path to be excluded,
  note that the path is the path after packaging, which can be viewed through `unzip -l`, example:

  ```python
  exclusions = ['google/protobuf/*'],
  ```

## py_test

Compile and run the python test code.

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

We usually use the `unittest` library for python unit testing.

## Using Protobuf

The proto file needs to be described by [proto_library](idl.md#proto_library), which is introduced in the deps of py_*.
The corresponding python protobuf encoding and decoding code will be automatically generated during blade build.

The import path rule in the python code is to start from the workspace root, replace `/` with `.`,
and replace the `.proto` at the end of the file name with `_pb2`, for example:

```python
# proto file's path is //common/base/user_info.proto
import common.base.user_info_pb2
```
