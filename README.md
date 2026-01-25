# Blade Build System

[![license NewBSD](https://img.shields.io/badge/License-NewBSD-yellow.svg)](COPYING)
[![Python](https://img.shields.io/badge/language-python2,3-blue.svg)](https://www.python.org/)
[![Code Style](https://img.shields.io/badge/code%20style-google-blue.svg)](https://google.github.io/styleguide/pyguide.html)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macos-lightgrey.svg)](doc/en/prerequisites.md)

![Blade Build](/image/blade-200x400.png "Blade Build")

English | [简体中文](README-zh.md)

An easy-to-use, fast, and modern build system for trunk-based development in a large-scale monorepo codebase.

## Build Status

[![Build Status](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml/badge.svg)](https://github.com/blade-build/blade-build/actions/workflows/python-package.yml)
[![codebeat badge](https://codebeat.co/badges/e0d861b7-47cc-4023-9784-7d54246a3576)](https://codebeat.co/projects/github-com-chen3feng-blade-build-master)
[![Coverage](https://coveralls.io/repos/chen3feng/blade-build/badge.svg?branch=master)](https://coveralls.io/github/chen3feng/blade-build)
[![Downloads](https://img.shields.io/github/downloads/blade-build/blade-build/total.svg)](https://github.com/blade-build/blade-build/releases)

## Demo

First, let's see a cool demo:

[![asciicast](https://asciinema.org/a/o9uQ2uia4OVqghXUid7XSNjv1.svg)](https://asciinema.org/a/o9uQ2uia4OVqghXUid7XSNjv1)

## Releases

The code on the master branch is the development version and should be considered as an alpha version.
Please prefer using the version on the tags in your formal environment.
We will release the verified version on the large-scale internal code base to the tag from time to time.

* Version 2.0 is released! It includes the following notable changes:

  * minimal Python version 2.7, support Python 3
  * Support Java, scala building
  * Full support for Python
  * Support custom extensions
  * Only use [ninja](doc/en/config.md#global_config) as backend build system, increases speed dramatically.

Please follow the [Upgrade Notes](doc/en/upgrade-to-v2.md) to upgrade.

## Stargazers over time

[![Stargazers over time](https://starchart.cc/blade-build/blade-build.svg)](https://starchart.cc/blade-build/blade-build)

## Origin

Blade is designed to be a modern build system. It is powerful and easy to use. It supports building
multiple languages, such as c/c++, Java, Python, Scala, protobuf, etc. It analyzes the
target dependency automatically and integrates compiling, linking, testing(including incremental
testing and parallel testing), and static code inspection together.
It aims to improve the clarity and simplicity of the building rules for a project.

Blade is primarily positioned for large C++ projects on Linux, closely integrated with development workflows such as unit testing, continuous integration, and coverage statistics. Like Unix text filtering programs, it maintains relative independence and can run standalone. Currently, it focuses on supporting i386/x86_64 Linux, with potential future support for other Unix-like systems.

During the development of [Tencent's "Typhoon" cloud computing platform](/doc/Hadoop-in-China-2011-Typhoon.mhtml), to solve the complexity and difficulty issues of GNU Make and Autotools, and referencing [some articles from Google's engineering blog](http://google-engtools.blogspot.hk/2011/08/build-in-cloud-how-build-system-works.html), we developed this entirely new build system. The entire system is based on multiple declarative build scripts where you only need to declare what targets to build, their source code, and their direct dependencies on other targets, without specifying how to build. This greatly reduces usage difficulty and improves development efficiency.

In 2012, Blade was open-sourced, becoming Tencent's earliest open-source project. It has now been widely adopted across Tencent's advertising systems, WeChat backend services, Tencent gaming backend services, Tencent's basic infrastructure, as well as other companies like Xiaomi, Baidu, and iQiyi. We have also received multiple Pull Requests from both inside and outside the company.

After being open-sourced, the code was hosted on googlecode, and due to googlecode's later closure, it was migrated to chen3feng's personal git repository for continued maintenance.

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
