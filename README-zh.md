# Blade 构建系统

[![Website](https://img.shields.io/badge/website-blade--build.github.io-1f6feb.svg)](https://blade-build.github.io/)
[![license NewBSD](https://img.shields.io/badge/License-NewBSD-yellow.svg)](COPYING)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Code Style](https://img.shields.io/badge/code%20style-google-blue.svg)](https://google.github.io/styleguide/pyguide.html)

![Blade Build](image/blade-200x400.png "Blade Build")

[English](README.md) | 简体中文

Blade 是一款面向大规模 monorepo 环境和主干开发（trunk-based development）的现代化、高性能源代码构建系统。

## 构建状态

[![Linux](https://img.shields.io/github/actions/workflow/status/blade-build/blade-build/python-package.yml?branch=master&logo=linux&logoColor=white&label=Linux)](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml)
[![macOS](https://img.shields.io/github/actions/workflow/status/blade-build/blade-build/macos-ci.yml?branch=master&logo=apple&logoColor=white&label=macOS)](https://github.com/blade-build/blade-build/actions/workflows/macos-ci.yml)
[![Windows](https://img.shields.io/github/actions/workflow/status/blade-build/blade-build/windows-ci.yml?branch=master&logo=windows&logoColor=white&label=Windows)](https://github.com/blade-build/blade-build/actions/workflows/windows-ci.yml)
[![Coverage](https://coveralls.io/repos/blade-build/blade-build/badge.svg?branch=master)](https://coveralls.io/github/blade-build/blade-build)
[![Downloads](https://img.shields.io/github/downloads/blade-build/blade-build/total.svg)](https://github.com/blade-build/blade-build/releases)

## 简介

2010 年时，在腾讯[「台风」云计算平台](doc/Hadoop-in-China-2011-Typhoon.mhtml)的研发过程中，我们深刻体会到 GNU Make、Autotools 等传统构建系统在大规模环境下的不足。受 [Google 工程博客上一系列文章](http://google-engtools.blogspot.hk/2011/08/build-in-cloud-how-build-system-works.html) 的启发，我们设计和实现了 Blade 构建系统。

Blade 是一款现代化的高性能构建系统，既追求强大的能力，也追求良好的使用体验，目标是把程序员从繁琐的构建工作中解放出来。它原生支持 C/C++、Java、Python、Scala、Protocol Buffers 等多种语言，自动分析目标间的依赖，并将编译、链接、测试（支持增量测试与并行测试）以及静态代码分析无缝整合在一起。

Blade 在简化构建配置的同时，也为复杂项目的构建提供足够的灵活性，并内置集成了大量现代编译器特性，如测试覆盖率、内存错误诊断与分析、编译器优化等。

Blade 主要面向大型 C++ 项目，与研发流程（单元测试、持续集成、覆盖率统计等）紧密配合；同时也奉行 Unix 哲学，可以单独运行。Blade 将 Linux（i386/x86_64/aarch64）、macOS（clang）和 Windows（MSVC）作为一等平台支持。

整个系统基于若干声明式的构建脚本。在这些脚本中，开发者只需声明「构建什么」（目标、源文件、直接依赖），而不必描述「如何构建」。这种思路大幅降低了配置复杂度，也显著提升了开发效率与可维护性。

借助 Blade，只需一行命令即可完成多个目标的编译、链接与测试。例如：

递归构建并测试 `common` 目录下的所有目标：

```bash
blade test common...
```

以 debug 模式构建与测试：

```bash
blade test -pdebug common...
```

启用某个 sanitizer 进行构建与测试：

```bash
blade test --sanitizer=address common...
```

## 为何而生

Blade 能追踪库之间的依赖关系。例如，库 `foo` 依赖库 `common`，只需在 `foo` 的 BUILD 文件中声明这层依赖：

```python
cc_library(
    name = 'foo',
    srcs = ...,
    hdrs = ...,
    deps = ':common'
)
```

此时，使用 `foo` 的程序即便没有直接使用 `common`，也只需列出 `foo` 作为依赖，而无需显式声明 `common`：

```python
cc_binary(
    name = 'my_app',
    srcs = ...,
    deps = ':foo'
)
```

这样一来，当库的实现发生变化、或新增、删除依赖时，库的使用方无需同步修改。Blade 会自动维护这层间接依赖；在构建 `my_app` 时，也会自动检查 `foo` 与 `common` 是否需要更新。

## 演示

我们看一个真实的演示来感受 Blade 的简洁和高效：

[![asciicast](https://asciinema.org/a/1203812.svg)](https://asciinema.org/a/1203812)

## 特点

* **原生集成 [vcpkg](https://github.com/microsoft/vcpkg) 管理 C/C++ 第三方库。** 长期以来在 Blade 中使用第三方库都比较麻烦；随着 vcpkg 的成熟，Blade 将它作为一等的第三方包管理工具集成进来——在 `deps` 中写 `vcpkg#<port>:<lib>`，Blade 即自动安装并链接，支持版本固定与二进制缓存。详见[使用 vcpkg 包](doc/zh_CN/build_rules/vcpkg.md)。
* 自动分析头文件依赖关系，重新构建受影响的代码。
* 增量编译与链接，只重建真正需要重建的部分。
* 自动计算库的间接依赖；库作者只需声明直接依赖，构建时自动检查间接依赖是否需要重建。
* 可从代码树任意子目录启动构建。
* 支持一次递归构建多个目录下的所有目标，也支持只构建指定目标。
* 无论构建什么目标，其依赖都会被自动跟随更新。
* 内置 debug / release 两种构建类型。
* 彩色高亮展示构建过程中的错误信息。
* 支持 ccache。
* 支持 distcc。
* 支持多平台目标构建。
* 支持构建时选择编译器（不同版本的 GCC、Clang 等）。
* 支持 protobuf、lex、yacc、SWIG 的构建。
* 支持自定义构建规则。
* 支持在命令行一次运行多个测试。
* 支持并行测试（多个测试进程并发运行）。
* 支持增量测试（无需重新运行的测试自动跳过）。
* 集成 gperftools，自动检测测试程序中的内存泄漏。
* 为构建脚本提供 Vim 语法高亮。
* 采用 git 风格的子命令式命令行接口。
* 支持 Bash 命令行补全。
* 使用 Python 编写，无需编译，直接安装使用。

彻底避免以下问题：

* 头文件已更新，但受影响的模块未能重新构建。
* 所依赖的库需要更新，但在构建时未被同步更新（例如某子目录的依赖被遗漏）。

## Blade 版本历史

Blade 至今共有三个大版本。

Blade 1 是早期版本，其目标是提供一个简单易用的构建系统，后端是 [Scons](https://scons.org/) 构建系统。

Blade 2 把后端升级到了 [Ninja](https://ninja-build.org/) 构建系统，大幅度地提高了性能。

目前最新的 Blade 是 Blade 3，其目标是提供一个现代化的构建系统。Blade 3 把项目从一个仅限 Linux、以 GCC 为中心的工具，升级为**三平台、多工具链**的现代构建系统。主要亮点：

* **三平台，一份 BUILD** —— Linux + macOS（clang）+ Windows（MSVC），通过 `cc_toolchain_config` 按构建选择。
* **原生 [vcpkg](https://github.com/microsoft/vcpkg) 集成** —— 版本锁定、隔离的 C/C++ 第三方库，用 `vcpkg#port:lib` 引用，相当于 C++ 版的 `maven_jar`。
* **Sanitizer 与覆盖率** —— `--sanitizer=address,…`（ASan/UBSan/LSan/TSan/MSan；MSVC 上的 ASan）与 `--coverage`（C/C++ / Go / Python 的 HTML 报告），对既有目标树生效，无需改 BUILD。
* **性能剖析引导与链接期优化** —— 插桩式 PGO、采样式 PGO / AutoFDO，以及 LTO / ThinLTO，在 gcc / clang / MSVC / clang-cl 上统一。见 [C/C++ 优化](doc/zh_CN/optimization.md)。
* **跨平台符号控制** —— `export_map` / `linker_script` 在 GCC / clang / MSVC 上一致翻译。
* **更强的依赖卫生** —— 新增 `unused-deps` 检查与静态未定义符号检查，与既有的 `missing-deps` 检查并列。
* **现代化代码库** —— 仅 Python 3.10+（移除 Python 2），全量类型标注 + pyright，完善的单元与跨仓库 E2E 测试。

升级细节请参考[升级到 V3 版](doc/zh_CN/upgrade-to-v3.md)。

## 版本发布

当前最新的稳定发布是 [`v3.0.0`](https://github.com/blade-build/blade-build/releases/tag/v3.0.0)；`master` 分支是 Blade 3 的开发主线。完整列表见 [Releases](https://github.com/blade-build/blade-build/releases)，升级细节请参考[升级到 V3 版](doc/zh_CN/upgrade-to-v3.md)。

如果需要 Blade 2，请使用 [`v2`](https://github.com/blade-build/blade-build/tree/v2) 分支或 [v2.1.0 tag](https://github.com/blade-build/blade-build/releases/tag/v2.1.0)；升级细节参考 [V2 升级说明](doc/zh_CN/upgrade-to-v2.md)。

## 文档

* [完整文档](https://blade-build.github.io/docs/zh/)

## 贡献者

2012 年，Blade 对外开源，成为腾讯公司最早的开源项目之一。此后，Blade 在腾讯技术栈中获得了广泛应用，覆盖广告平台、微信后台服务、游戏服务端、基础架构等核心场景；在腾讯之外，小米、百度、爱奇艺等多家公司也在使用 Blade。

Blade 由此形成了活跃的贡献者社区，收到来自公司内外的众多 Pull Request。项目最初托管在 Google Code 上，在 Google Code 停止服务后，迁移到 chen3feng 的个人仓库继续维护与演进，并最终迁移到这里。

[![Contributers](https://contrib.rocks/image?repo=blade-build/blade-build)](https://github.com/blade-build/blade-build/graphs/contributors)

## Star History

即使您没有时间和精力贡献，也热烈欢迎 star。

<a href="https://www.star-history.com/?repos=blade-build%2Fblade-build&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&legend=top-left" />
 </picture>
</a>

## 致谢

* Blade 的设计受到了 Google 公开分享的构建系统经验启发，特别是他们工程博客上的这篇文章：
  [Build in the Cloud: How the Build System Works](http://google-engtools.blogspot.com/2011/08/build-in-cloud-how-build-system-works.html)。
  2015 年，Google 将经过部分重写的版本以新的名字 `bazel` 对外开源。

* Blade 在内部生成 [Ninja](https://ninja-build.org/) 脚本来驱动构建，因此运行时依赖 Ninja。
* [Python](http://www.python.org) 是一门简单易用而又强大的语言，我们非常喜欢。

我们的理念：解放程序员，提升生产力，用工具解决非创造性的技术问题。

欢迎使用 Blade，也欢迎你参与改进，我们期待你的贡献。
