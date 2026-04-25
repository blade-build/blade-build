# Blade Build System

[![license NewBSD](https://img.shields.io/badge/License-NewBSD-yellow.svg)](COPYING)
[![Python](https://img.shields.io/badge/language-python2,3-blue.svg)](https://www.python.org/)
[![Code Style](https://img.shields.io/badge/code%20style-google-blue.svg)](https://google.github.io/styleguide/pyguide.html)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos-lightgrey.svg)](doc/zh_CN/prerequisites.md)

![Blade Build](/image/blade-200x400.png "Blade Build")

一个现代化的高性能构建系统，专为大规模单代码库环境中的主干开发优化设计。

Blade is a modern, high-performance build system optimized for trunk-based development in large-scale monorepo environments.

[English](README.md) | 简体中文

## Build Status

[![Build Status](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml/badge.svg)](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml)
[![codebeat badge](https://codebeat.co/badges/e0d861b7-47cc-4023-9784-7d54246a3576)](https://codebeat.co/projects/github-com-chen3feng-blade-build-master)
[![Coverage](https://coveralls.io/repos/chen3feng/blade-build/badge.svg?branch=master)](https://coveralls.io/github/chen3feng/blade-build)
[![Downloads](https://img.shields.io/github/downloads/chen3feng/blade-build/total.svg)](https://github.com/chen3feng/blade-build/releases)

## 演示

我们先来看一个漂亮的演示：

[![asciicast](https://asciinema.org/a/o9uQ2uia4OVqghXUid7XSNjv1.svg)](https://asciinema.org/a/o9uQ2uia4OVqghXUid7XSNjv1)

## 发布

master 分支上的代码是开发版，应当视为 alpha 版。正式环境请优先考虑使用 tag 上的版本。我们会不定期地把内部大规模代码库上验证过的版本发布到 tag 上。

* Blade 2.0 现已发布，包含以下主要增强功能：

  * Python 最低版本要求：2.7，完全支持 Python 3
  * Java 和 Scala 构建支持
  * 全面的 Python 语言支持
  * 自定义扩展框架
  * 独家使用 [Ninja](doc/zh_CN/config.md#global_config) 作为后端构建系统，带来显著的性能提升

具体请查看[升级说明](doc/zh_CN/upgrade-to-v2.md)。

## Stargazers over time

[![Stargazers over time](https://starchart.cc/blade-build/blade-build.svg)](https://starchart.cc/blade-build/blade-build)

## 源起

Blade 是一个现代化的高性能构建系统，旨在解决大规模软件开发中的复杂性。虽然 GNU Make 等传统工具功能强大，但在企业环境中直接使用往往会带来显著的操作挑战。

## 传统构建系统的局限性

**依赖管理复杂性：**
- 手动创建 Makefile 经常导致依赖关系规范不完整
- 不一致的依赖跟踪导致增量构建不可靠

**操作效率低下：**
- 频繁的 `make clean` 操作抵消了 Make 增量构建的优势
- 在包含数千个目标的单代码库环境中出现可扩展性限制

**开发者体验挑战：**
- 高学习曲线阻碍团队采用和生产力
- Autotools 自动化承诺通常需要复杂的命令序列
- 项目间缺乏标准化约定

## Blade 的企业级解决方案

在腾讯公司[「台风」云计算平台](http://storage.it168.com/a2011/1203/1283/000001283196.shtml)开发期间，Blade 作为一个为大规模企业级开发设计的下一代构建系统应运而生。

**关键设计原则：**
- **声明式配置：** BUILD 文件指定构建内容，而非构建方式
- **自动依赖管理：** 全面的依赖跟踪，无需手动指定
- **高性能：** 针对大规模单代码库环境优化
- **开发者生产力：** 直观语法配合强大的自动化能力

**企业级特性：**
- 支持主干开发，便于持续集成
- 多语言构建能力（C/C++、Java、Python 等）
- 先进的缓存机制加速构建
- 全面的测试和部署集成

现已开源，Blade 结合了快速开发所需的简洁性和企业级项目所需的健壮性。

## 为何而生

首先，Blade 解决了依赖问题。
当你在构建某些目标时，头文件有变化，会自动重新构建。
最方便的是，Blade 也能追踪库文件的依赖关系。比如
库 foo 依赖库 common，那么在库 foo 的 BUILD 文件中列入依赖：

```python
cc_library(
    name = 'foo',
    srcs = ...,
    hdrs = ...,
    deps = ':common'
)
```

那么对于使用 foo 的程序，如果没有直接用到 common，那么就只需要列出 foo，并不需要列出 common。

```python
cc_binary(
    name = 'my_app',
    srcs = ...,
    deps = ':foo'
)
```

这样当你的库实现发生变化，增加或者减少库时，并不需要通知库的用户一起改动，Blade 自动维护这层间接的依赖关系。当构建 my_app 时，也会自动检查 foo 和 common 是否也需要更新。

说到易用性，除了依赖关系的自动维护，Blade 还可以做到，用户只需要敲一行命令，就能把整个目录树的编译链接和单元测试全部搞定。例如：

递归构建和测试 common 目录下所有的目标

```bash
blade test common...
```

以 32 位模式构建和测试

```bash
blade test -m32 common...
```

以调试模式构建和测试

```bash
blade test -pdebug common...
```

显然，你可以组合这些标志

```bash
blade test -m32 -pdebug common...
```

## 特点

* 自动分析头文件依赖关系，构建受影响的代码。
* 增量编译和链接，只构建因变更受影响而需要重新构建的代码。
* 自动计算库的间接依赖，库的作者只需要写出直接依赖，构建时自动检查所依赖的库是否需要重新构建。
* 在任意代码树的任意子目录下都能构建。
* 支持一次递归构建多个目录下的所有目标，也支持只构建任意的特定的目标。
* 无论构建什么目标，这些目标所依赖的目标也会被自动连坐更新。
* 内置 debug/release 两种构建类型。
* 彩色高亮构建过程中的错误信息。
* 支持 ccache
* 支持 distcc
* 支持基于构建多平台目标
* 支持构建时选择编译器（不同版本的 gcc、clang 等）
* 支持编译 protobuf、lex、yacc、swig
* 支持自定义规则
* 支持测试，在命令行跑多个测试
* 支持并行测试（多个测试进程并发运行）
* 支持增量测试（无需重新运行的测试程序自动跳过）
* 集成 gperftools，自动检测测试程序的内存泄露
* 构建脚本 vim 语法高亮
* svn 式的子命令命令行接口。
* 支持 bash 命令行补全
* 用 python 编写，无需编译，直接安装使用。

彻底避免以下问题：

* 头文件更新，受影响的模块没有重新构建。
* 被依赖的库需要更新，而构建时没有被更新，比如某子目录依赖

## 文档

看到这里，你应该觉得 Blade 是个不错的工具，那么，阅读[完整文档](doc/zh_CN/README.md)，开始使用吧。

如果遇到有问题，可以试试先查一下[FAQ](doc/zh_CN/FAQ.md)，也许有你需要的信息。

## 贡献者

[![Contributers](https://contrib.rocks/image?repo=blade-build/blade-build)](https://github.com/blade-build/blade-build/graphs/contributors)

## 致谢

* Blade 是受 Google 官方博客发表的这篇文章启发而开发的：
  [云构建：构建系统是如何工作的](http://google-engtools.blogspot.com/2011/08/build-in-cloud-how-build-system-works.html)。
  后来在 2015 年，他们把部分重写后系统的以 `bazel` 的新名字开源。
* Blade 生成 [Ninja](https://ninja-build.org/) 脚本进行构建，因此 Blade 的运行还需要依赖 Ninja。
* [Python](http://www.python.org) 是一种简单易用而又强大的语言，我们喜欢 python。

Google 开放的一些库强大而好用，我们很喜欢，我们把对这些库的支持集成进了 Blade 中，既方便了库的使用，又增强了 Blade，这些库包括：

- [glog](https://google.github.io/glog/stable/)
- [protobuf](https://github.com/protocolbuffers/protobuf)
- [gtest](https://github.com/google/googletest)
- [gperftools](https://github.com/gperftools/gperftools)

我们的理念：解放程序员，提高生产力。用工具来解决非创造性的技术问题。

欢迎使用以及帮助我们改进 Blade，我们期待你的贡献。
