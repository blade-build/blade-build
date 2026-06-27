# Blade Build System

[![Website](https://img.shields.io/badge/website-blade--build.github.io-1f6feb.svg)](https://blade-build.github.io/)
[![license NewBSD](https://img.shields.io/badge/License-NewBSD-yellow.svg)](COPYING)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Code Style](https://img.shields.io/badge/code%20style-google-blue.svg)](https://google.github.io/styleguide/pyguide.html)

![Blade Build](image/blade-200x400.png "Blade Build")

English | [简体中文](README-zh.md)

A modern, high-performance build system optimized for trunk-based development in large-scale monorepo environments.

## Build Status

[![Linux](https://img.shields.io/github/actions/workflow/status/blade-build/blade-build/python-package.yml?branch=master&logo=linux&logoColor=white&label=Linux)](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml)
[![macOS](https://img.shields.io/github/actions/workflow/status/blade-build/blade-build/macos-ci.yml?branch=master&logo=apple&logoColor=white&label=macOS)](https://github.com/blade-build/blade-build/actions/workflows/macos-ci.yml)
[![Windows](https://img.shields.io/github/actions/workflow/status/blade-build/blade-build/windows-ci.yml?branch=master&logo=windows&logoColor=white&label=Windows)](https://github.com/blade-build/blade-build/actions/workflows/windows-ci.yml)
[![Coverage](https://coveralls.io/repos/blade-build/blade-build/badge.svg?branch=master)](https://coveralls.io/github/blade-build/blade-build)
[![Downloads](https://img.shields.io/github/downloads/blade-build/blade-build/total.svg)](https://github.com/blade-build/blade-build/releases)

## Demo

First, let's see a cool demo:

[![asciicast](https://asciinema.org/a/1203812.svg)](https://asciinema.org/a/1203812)

## Blade 3

Blade 3 takes the project from a Linux-only, GCC-focused tool to a **three-platform, multi-toolchain** modern build system. Highlights:

- **Three platforms, one BUILD file** — Linux + macOS (clang) + Windows (MSVC), selectable per build via `cc_toolchain_config`.
- **Native [vcpkg](https://github.com/microsoft/vcpkg) integration** — version-pinned, hermetic C/C++ third-party libraries via `vcpkg#port:lib`, the `maven_jar` analog for C++.
- **Sanitizers & coverage** — `--sanitizer=address,…` (ASan/UBSan/LSan/TSan/MSan; ASan on MSVC) and `--coverage` (C/C++ / Go / Python HTML reports) on an existing target tree, no BUILD changes.
- **Profile-guided & link-time optimization** — instrumentation PGO, sample-based PGO / AutoFDO, and LTO / ThinLTO, unified across gcc / clang / MSVC / clang-cl. See [C/C++ Optimization](doc/en/optimization.md).
- **Cross-platform symbol control** — `export_map` / `linker_script` translated consistently across GCC / clang / MSVC.
- **Stronger dependency hygiene** — an `unused-deps` check and a static undefined-symbol check join the existing `missing-deps` check.
- **Modernized codebase** — Python 3.10+ only (Python 2 removed), full type annotations with pyright, comprehensive unit + cross-repo E2E tests.

See the [Upgrade to V3](doc/en/upgrade-to-v3.md) guide for details.

## Star History

<a href="https://www.star-history.com/?repos=blade-build%2Fblade-build&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&legend=top-left" />
 </picture>
</a>

## Origin

Blade is engineered as a modern, high-performance build system that combines power with ease of use. It provides comprehensive support for multiple programming languages including C/C++, Java, Python, Scala, Protocol Buffers, and more. The system automatically analyzes target dependencies and seamlessly integrates compilation, linking, testing (with support for incremental and parallel testing), and static code analysis.

Designed to enhance development productivity, Blade simplifies build configuration while maintaining robust functionality for complex projects.

Blade is primarily positioned for large C++ projects, closely integrated with development workflows such as unit testing, continuous integration, and coverage statistics. Like Unix text filtering programs, it maintains relative independence and can run standalone. It supports Linux (i386/x86_64/aarch64), macOS (clang), and Windows (MSVC) as first-class platforms.

During the development of [Tencent's "Typhoon" cloud computing platform](doc/Hadoop-in-China-2011-Typhoon.mhtml), we identified significant challenges with GNU Make and Autotools in large-scale environments. Inspired by insights from [Google's engineering blog](http://google-engtools.blogspot.hk/2011/08/build-in-cloud-how-build-system-works.html), we engineered Blade as a declarative build system.

The system utilizes declarative build scripts where developers specify what to build (targets, sources, and direct dependencies) rather than how to build it. This approach dramatically reduces configuration complexity while significantly improving development efficiency and maintainability.

Blade was open-sourced in 2012 as one of Tencent's earliest open-source initiatives. The system has achieved widespread adoption across Tencent's technology stack, including advertising platforms, WeChat backend services, gaming infrastructure, and core infrastructure systems. Beyond Tencent, Blade has been deployed at major technology companies including Xiaomi, Baidu, and iQiyi.

The project has fostered an active contributor community, receiving numerous Pull Requests from both internal and external developers. Originally hosted on Google Code, the project was migrated to chen3feng's personal repository following Google Code's deprecation, where it continues to be actively maintained and developed.

With Blade, you can compile, link, and test multiple targets by just inputting one simple command line.
For example:

Build and test all targets in the common directory recursively.

```bash
blade test common...
```

Build and test targets in debug mode

```bash
blade test -pdebug common...
```

Build and test with a specific sanitizer enabled:

```bash
blade test --sanitizer=address common...
```

## Why It Exists

First and foremost, Blade solves dependency problems. When you build certain targets, if header files have changed, it will automatically rebuild them.

Most conveniently, Blade can also track library file dependencies. For example, if library foo depends on library common, then in library foo's BUILD file, you list the dependency:

```python
cc_library(
    name = 'foo',
    srcs = ...,
    hdrs = ...,
    deps = ':common'
)
```

Then for programs using foo, if they don't directly use common, you only need to list foo, not common:

```python
cc_binary(
    name = 'my_app',
    srcs = ...,
    deps = ':foo'
)
```

This way, when your library implementation changes, adding or removing libraries, you don't need to notify library users to make changes together. Blade automatically maintains this layer of indirect dependencies. When building my_app, it will also automatically check whether foo and common need to be updated.

In terms of ease of use, besides automatic dependency maintenance, Blade can also achieve that users only need to type one command line to handle compilation, linking, and unit testing for the entire directory tree.

## Features

* **Native [vcpkg](https://github.com/microsoft/vcpkg) integration for C/C++ third-party libraries.** Using third-party libraries in Blade has long been cumbersome; as vcpkg has matured, Blade now integrates it as a first-class package manager — declare `vcpkg#<port>:<lib>` in `deps` and Blade installs and links them, with version pinning and a binary cache. See [Using vcpkg packages](doc/en/build_rules/vcpkg.md).
* Automatic analysis of header file dependencies, building affected code.
* Incremental compilation and linking, only building code that needs to be rebuilt due to changes.
* Automatic calculation of indirect library dependencies - library authors only need to write direct dependencies, and builds automatically check if dependent libraries need rebuilding.
* Ability to build from any subdirectory in any code tree.
* Support for recursive building of all targets in multiple directories at once, as well as building only specific arbitrary targets.
* Whatever targets you build, their dependent targets are also automatically updated.
* Built-in debug/release build types.
* Colorful highlighting of error messages during build process.
* Support for ccache.
* Support for distcc.
* Support for building multi-platform targets.
* Support for compiler selection during build (different versions of gcc, clang, etc.).
* Support for compiling protobuf, lex, yacc, swig.
* Support for custom rules.
* Support for testing, running multiple tests from command line.
* Support for parallel testing (multiple test processes running concurrently).
* Support for incremental testing (unchanged test programs are automatically skipped).
* Integration with gperftools for automatic memory leak detection in test programs.
* Vim syntax highlighting for build scripts.
* git-style subcommand command line interface.
* Support for bash command line completion.
* Written in Python, no compilation needed, direct installation and use.

## Problems Avoided

Completely avoiding the following problems:

* Header files updated, but affected modules were not rebuilt.
* Dependent libraries needed updates but were not updated during build, such as certain subdirectory dependencies.

## Releases

The latest stable release is [`v3.0.0`](https://github.com/blade-build/blade-build/releases/tag/v3.0.0); the `master` branch is the active development line for Blade 3. See all [Releases](https://github.com/blade-build/blade-build/releases), and the [Upgrade to V3](doc/en/upgrade-to-v3.md) guide.

For Blade 2, use the [`v2`](https://github.com/blade-build/blade-build/tree/v2) branch or the [v2.1.0 tag](https://github.com/blade-build/blade-build/releases/tag/v2.1.0); see the [V2 Upgrade Notes](doc/en/upgrade-to-v2.md).

## Documentation

* [Full Documentation](doc/en/README.md)
* [FAQ](doc/en/FAQ.md)

## Contributers

[![Contributers](https://contrib.rocks/image?repo=blade-build/blade-build)](https://github.com/blade-build/blade-build/graphs/contributors)

## Credits

* Blade is inspired by Google's public information about their build system. Here is a reference article from Google's official blog:
  [build in cloud: how build system works](http://google-engtools.blogspot.com/2011/08/build-in-cloud-how-build-system-works.html).

  Later in 2015, they released it with a partially rewritten version as the `bazel` open-source build system.

* Blade generates [Ninja](https://ninja-build.org/) script internally, so of course it depends on Ninja.
* [Python](http://www.python.org) is a powerful and easy-to-used language, we like python.

Some libraries open-sourced by Google, such as:

* [glog](https://google.github.io/glog/stable/)
* [protobuf](https://github.com/protocolbuffers/protobuf)
* [gtest](https://github.com/google/googletest)
* [gperftools](https://github.com/gperftools/gperftools)

They are handy and powerful; we have integrated these libraries.

Our philosophy: Liberate programmers, improve productivity. Use tools to solve non-creative technical problems.

Welcome to use and help us improve Blade, we look forward to your contributions.
