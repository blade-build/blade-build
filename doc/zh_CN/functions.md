# 构建函数

一些 BUILD 文件中可以调用的函数

## glob

```python
glob(include, exclude=[], allow_empty=False)
```

Glob 是一个返回在源代码目录中匹配某些模式的文件的辅助函数。模式可以包含一些 shell 样式的通配符，比如`*`、`?` 和 `[字符集]`、，另外，`**` 匹配任意级别的子目录。
你可以用 `exclude` 来排除一些文件。include 和 exclude 都支持 list。

示例：

```python
...
    srcs = glob(['*.java', 'src/main/java/**/*.java'], exclude=['*Test.java'])
...
```

通常 glob 函数返回空结果视为错误，但是如果确实是符合你的预期，可以通过指定 `allow_empty=True` 来消除。
