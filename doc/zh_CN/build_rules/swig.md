# 构建 SWIG #

SWIG 是个帮助使用 C 或者 C++编写的软件能与其它各种高级编程语言进行嵌入联接的开发工具。

## swig_library ##

根据.i 文件生成相应的 python, java 和 php cxx 模块代码，并且生成对应语言的代码。

```python
swig_library(
    name = 'poppy_client',
    srcs = [
        'poppy_client.i'
    ],
    deps = [
        ':poppy_swig_wrap'
    ],
    warning='yes',
    java_package='com.soso.poppy.swig',   # 生成的java文件的所在package名称
    java_lib_packed=1, # 表示把生成的libpoppy_client_java.so打包到依赖者的jar包里，如java_jar依赖这个swig_library
    optimize=['O3']    # 编译优化选项
)
```

* warning
这里的 warning 仅仅指 swig 编译参数 cpperraswarn 是否被指定了，swig_library 默认使用非标准编译告警级别（没有那么严格）。
