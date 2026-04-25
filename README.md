# Blade Build System

[![license NewBSD](https://img.shields.io/badge/License-NewBSD-yellow.svg)](COPYING)
[![Python](https://img.shields.io/badge/language-python2,3-blue.svg)](https://www.python.org/)
[![Code Style](https://img.shields.io/badge/code%20style-google-blue.svg)](https://google.github.io/styleguide/pyguide.html)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos-lightgrey.svg)](doc/en/prerequisites.md)

![Blade Build](/image/blade-200x400.png "Blade Build")

English | [简体中文](README-zh.md)

A modern, high-performance build system optimized for trunk-based development in large-scale monorepo environments.

## Build Status

[![Build Status](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml/badge.svg)](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml)
[![codebeat badge](https://codebeat.co/badges/e0d861b7-47cc-4023-9784-7d54246a3576)](https://codebeat.co/projects/github-com-chen3feng-blade-build-master)
[![Coverage](https://coveralls.io/repos/chen3feng/blade-build/badge.svg?branch=master)](https://coveralls.io/github/chen3feng/blade-build)
[![Downloads](https://img.shields.io/github/downloads/chen3feng/blade-build/total.svg)](https://github.com/chen3feng/blade-build/releases)

## Demo

First, let's see a cool demo:

[![asciicast](https://asciinema.org/a/o9uQ2uia4OVqghXUid7XSNjv1.svg)](https://asciinema.org/a/o9uQ2uia4OVqghXUid7XSNjv1)

## Releases

The code on the master branch is the development version and should be considered as an alpha version.
Please prefer using the version on the tags in your formal environment.
We will release the verified version on the large-scale internal code base to the tag from time to time.

* Version 2.0 is now available with the following major enhancements:

  * Minimum Python version requirement: 2.7, with full Python 3 support
  * Java and Scala build support
  * Comprehensive Python language support
  * Custom extension framework
  * Exclusive use of [Ninja](doc/en/config.md#global_config) as the backend build system, delivering significant performance improvements

Please follow the [Upgrade Notes](doc/en/upgrade-to-v2.md) to upgrade.

## Stargazers over time

[![Stargazers over time](https://starchart.cc/blade-build/blade-build.svg)](https://starchart.cc/blade-build/blade-build)

## Origin

Blade is engineered as a modern, high-performance build system that combines power with ease of use. It provides comprehensive support for multiple programming languages including C/C++, Java, Python, Scala, Protocol Buffers, and more. The system automatically analyzes target dependencies and seamlessly integrates compilation, linking, testing (with support for incremental and parallel testing), and static code analysis.

Designed to enhance development productivity, Blade simplifies build configuration while maintaining robust functionality for complex projects.

Blade is primarily positioned for large C++ projects on Linux, closely integrated with development workflows such as unit testing, continuous integration, and coverage statistics. Like Unix text filtering programs, it maintains relative independence and can run standalone. Currently, it focuses on supporting i386/x86_64 Linux, with potential future support for other Unix-like systems.

During the development of [Tencent's "Typhoon" cloud computing platform](/doc/Hadoop-in-China-2011-Typhoon.mhtml), we identified significant challenges with GNU Make and Autotools in large-scale environments. Inspired by insights from [Google's engineering blog](http://google-engtools.blogspot.hk/2011/08/build-in-cloud-how-build-system-works.html), we engineered Blade as a declarative build system.

The system utilizes declarative build scripts where developers specify what to build (targets, sources, and direct dependencies) rather than how to build it. This approach dramatically reduces configuration complexity while significantly improving development efficiency and maintainability.

Blade was open-sourced in 2012 as one of Tencent's earliest open-source initiatives. The system has achieved widespread adoption across Tencent's technology stack, including advertising platforms, WeChat backend services, gaming infrastructure, and core infrastructure systems. Beyond Tencent, Blade has been deployed at major technology companies including Xiaomi, Baidu, and iQiyi.

The project has fostered an active contributor community, receiving numerous Pull Requests from both internal and external developers. Originally hosted on Google Code, the project was migrated to chen3feng's personal repository following Google Code's deprecation, where it continues to be actively maintained and developed.

With Blade, you can compile, link, and test multiple targets by just inputting one simple command line.
For example:

Build and test all targets in the  common directory recursively.

```bash
blade test common...
```

Build and test targets as 32-bit

```bash
blade test -m32 common...
```

Build and test targets in debug mode

``` bash
blade test -pdebug common...
```

And you can combine the flags:

``` bash
blade test -m32 -pdebug common...
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
* SVN-style subcommand command line interface.
* Support for bash command line completion.
* Written in Python, no compilation needed, direct installation and use.

## Problems Avoided

Completely avoiding the following problems:

* Header files updated, but affected modules were not rebuilt.
* Dependent libraries needed updates but were not updated during build, such as certain subdirectory dependencies.

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
