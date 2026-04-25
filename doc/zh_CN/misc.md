# 辅助功能

## 辅助命令

### install

将 blade 命令的符号链接安装到 ~/bin 目录下。

### lsrc

列出当前目录下指定的源文件，以blade的srcs列表格式输出。

### genlibbuild

自动生成以目录名为库名的cc_library，以测试文件的名为名的cc_test，proto的BUILD文件，并假设这些测试都依赖这个库

### alt

在源代码目录和相应的构建结果目录之间来回跳转

## vim集成

我们编写了vim的blade语法文件，高亮显示blade关键字，install后就会自动生效。

我们编写了 Build 命令，使得可以在 vim 中直接执行 blade，并快速跳转到出错行（得益于 vim 的
[QuickFix](http://easwy.com/blog/archives/advanced-vim-skills-quickfix-mode/) 特性）。

使用时直接在 vim 的 : 模式输入（可带参数）

```vim
:Build blade build
```

即可构建。

这个命令的源代码在[这里](https://github.com/chen3feng/devenv/blob/master/_vimrc)。
