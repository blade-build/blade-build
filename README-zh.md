# Blade Build System

[![license NewBSD](https://img.shields.io/badge/License-NewBSD-yellow.svg)](COPYING)
[![Python](https://img.shields.io/badge/language-python2,3-blue.svg)](https://www.python.org/)
[![Code Style](https://img.shields.io/badge/code%20style-google-blue.svg)](https://google.github.io/styleguide/pyguide.html)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos-lightgrey.svg)](doc/zh_CN/prerequisites.md)

![Blade Build](/image/blade-200x400.png "Blade Build")

Blade是一个方便易用高性能的现代化代码构建系统，特别适合公司内的大规模代码库的敏捷构建，内置了对多种编程语言及单元测试框架的直接支持。

Blade is an easy-to-use, fast, and modern build system for trunk-based development in large-scale monorepo codebases. It supports building multiple programming languages.

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

* Blade 发布2.0，包含以下特性：
  * python 最低版本要求2.7，并支持 python 3
  * 对 Java，scala 构建的完善支持
  * 全面支持Python构建
  * 支持自定义扩展
  * 后端只支持[ninja](doc/zh_CN/config.md#global_config)构建系统，大幅度提高构建性能

具体请查看[升级说明](doc/zh_CN/upgrade-to-v2.md)。

## Stargazers over time

[![Stargazers over time](https://starchart.cc/blade-build/blade-build.svg)](https://starchart.cc/blade-build/blade-build)

## 源起

Blade 是一个现代构建系统，期望的目标是强大而好用，把程序员从构建的繁琐中解放出来。

Blade主要定位于linux下的大型C++项目，密切配合研发流程，比如单元测试，持续集成，覆盖率统计等。
但像unix下的文本过滤程序一样，保持相对的独立性，可以单独运行。目前重点支持i386/x86_64 Linux，未来可以考虑支持其他的类Unix系统。

在[腾讯公司“台风”云计算平台](/doc/Hadoop-in-China-2011-Typhoon.mhtml)开发过程中，为了解决 GNU Make，
Autotools 的难用和繁琐的问题，参考[Google工程博客上的一些文章](http://google-engtools.blogspot.hk/2011/08/build-in-cloud-how-build-system-works.html)，我们开发了这个全新的构建系统，整个系统基于多个声明式的构建脚本，在构建脚本里，
只需要声明要构建什么目标，目标的源代码，以及其直接依赖的其它目标，不需要说明如何构建。大大降低了使用难度，提高了开发效率。

2012年，Blade对外开源，成为腾讯公司最早的开源项目。目前已经广泛应用于腾讯广告系统、微信后台服务、腾讯游戏后台服务、腾讯基础架构，以及小米，百度，爱奇艺等其他公司，也收到了来自公司内外的多个Pull Requests。

代码开源后，托管到googlecode上，因后来googlecode关闭，迁移到chen3feng个人git仓库继续维护。

## 为何而生

首先，Blade解决了依赖问题。
当你在构建某些目标时，头文件有变化，会自动重新构建。
最方便的是，Blade也能追踪库文件的依赖关系。比如
库 foo 依赖库 common，那么在库 foo 的 BUILD 文件中列入依赖：

```python
cc_library(
    name = 'foo',
    srcs = ...,
    hdrs = ...,
    deps = ':common'
)
```

那么对于使用foo的程序，如果没有直接用到common，那么就只需要列出foo，并不需要列出common。

```python
cc_binary(
    name = 'my_app',
    srcs = ...,
    deps = ':foo'
)
```

这样当你的库实现发生变化，增加或者减少库时，并不需要通知库的用户一起改动，Blade自动维护这层间接的依赖关系。当构建my_app时，也会自动检查foo和common是否也需要更新。

说到易用性，除了依赖关系的自动维护，Blade还可以做到，用户只需要敲一行命令，就能把整个目录树的编译链接和单元测试全部搞定。例如：

递归构建和测试common目录下所有的目标

```bash
blade test common...
```

以32位模式构建和测试

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
* 支持构建时选择编译器（不同版本的gcc，clang等）
* 支持编译 protobuf，lex, yacc, swig
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
* 被依赖的库需要更新，而构建时没有被更新，比如某子目录依

## 文档

看到这里，你应该觉得Blade是个不错的工具，那么，阅读[完整文档](doc/zh_CN/README.md)，开始使用吧。

如果遇到有问题，可以试试先查一下[FAQ](doc/zh_CN/FAQ.md)，也许有你需要的信息。

## 贡献者

[![Contributers](https://contrib.rocks/image?repo=blade-build/blade-build)](https://github.com/blade-build/blade-build/graphs/contributors)

## 致谢

* Blade 是受 Google 官方博客发表的这篇文章启发而开发的：
  [云构建：构建系统是如何工作的](http://google-engtools.blogspot.com/2011/08/build-in-cloud-how-build-system-works.html)。
  后来在 2015 年，他们把部分重写后系统的以 `bazel` 的新名字开源。
* Blade 生成 [Ninja](https://ninja-build.org/) 脚本进行构建，因此 Blade 的运行还需要依赖 Ninja。
* [Python](http://www.python.org) 是一种简单易用而又强大的语言，我们喜欢python。

Google 开放的一些库强大而好用，我们很喜欢，我们把对这些库的支持集成进了Blade中，既方便了库的使用，又增强了 Blade，这些库包括：

- [glog](https://google.github.io/glog/stable/)
- [protobuf](https://github.com/protocolbuffers/protobuf)
- [gtest](https://github.com/google/googletest)
- [gperftools](https://github.com/gperftools/gperftools)

我们的理念：解放程序员，提高生产力。用工具来解决非创造性的技术问题。

欢迎使用以及帮助我们改进Blade，我们期待你的贡献。
