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

## Introduction

In 2010, during the development of [Tencent's "Typhoon" cloud computing platform](doc/Hadoop-in-China-2011-Typhoon.mhtml), we ran into the limits of traditional build systems such as GNU Make and Autotools at large scale. Inspired by a [series of articles on Google's engineering blog](http://google-engtools.blogspot.hk/2011/08/build-in-cloud-how-build-system-works.html), we designed and built Blade.

Blade frees programmers from tedious build chores: you write declarative BUILD scripts that say *what* to build (targets, sources, direct dependencies), not *how*. Blade resolves the dependencies between targets and unifies compilation, linking, testing (incremental and parallel), and static analysis. It natively supports C/C++, Java, Python, Scala, Protocol Buffers, and more.

Blade targets large C++ projects and fits closely into workflows like unit testing and continuous integration, yet follows the Unix philosophy and runs standalone; it treats Linux (i386/x86_64/aarch64), macOS (clang), and Windows (MSVC) as first-class platforms. It keeps configuration simple while giving complex projects flexibility, with extensive built-in integration of modern compiler features — test coverage, memory-error diagnosis and sanitizers, and compiler optimization.

Blade has been battle-tested on codebases of tens of millions of lines. For a real-world account of trunk-based development at that scale, see [*Tencent Ads: Trunk-Based Development on a 30-Million-Line Codebase*](https://cloud.tencent.com/developer/article/1804858) (in Chinese).

With Blade, a single command line compiles, links, and tests multiple targets. For example:

Recursively build and test all targets under the `common` directory:

```bash
blade test common...
```

Build and test in debug mode:

```bash
blade test -pdebug common...
```

Build and test with a sanitizer enabled:

```bash
blade test --sanitizer=address common...
```

## Why It Exists

Blade tracks dependencies between libraries. For example, if library `foo` depends on library `common`, you just declare that dependency in `foo`'s BUILD file:

```python
cc_library(
    name = 'foo',
    srcs = ...,
    hdrs = ...,
    deps = ':common'
)
```

Then a program that uses `foo`, even if it does not directly use `common`, only needs to list `foo` as a dependency, not `common`:

```python
cc_binary(
    name = 'my_app',
    srcs = ...,
    deps = ':foo'
)
```

This way, when a library's implementation changes, or dependencies are added or removed, the library's users don't need to change anything in step. Blade automatically maintains this layer of indirect dependencies; when building `my_app`, it also automatically checks whether `foo` and `common` need to be updated.

## User Interface

Let's look at a real demo to get a feel for how concise and efficient Blade is:

[![asciicast](https://asciinema.org/a/1203812.svg)](https://asciinema.org/a/1203812)

Beyond the command line, Blade has an official [VS Code extension](https://marketplace.visualstudio.com/items?itemName=blade-build.vscode-blade) that brings the targets explorer, build/run/test/debug, and BUILD-file language features into the editor:

[![Blade for VS Code](https://raw.githubusercontent.com/blade-build/vscode-blade/main/assets/demo.gif)](https://marketplace.visualstudio.com/items?itemName=blade-build.vscode-blade)

## Features

* **Native [vcpkg](https://github.com/microsoft/vcpkg) integration for C/C++ third-party libraries.** Using third-party libraries in Blade has long been cumbersome; as vcpkg has matured, Blade now integrates it as a first-class package manager — declare `vcpkg#<port>:<lib>` in `deps` and Blade installs and links them, with version pinning and a binary cache. See [Using vcpkg packages](doc/en/build_rules/vcpkg.md).
* Automatic analysis of header-file dependencies, rebuilding affected code.
* Incremental compilation and linking — only rebuild what actually needs rebuilding.
* Automatic calculation of indirect library dependencies — library authors declare only direct dependencies, and builds automatically check whether indirect dependencies need rebuilding.
* Ability to start a build from any subdirectory of the code tree.
* Recursively build all targets in multiple directories at once, or build only specific targets.
* Whatever targets you build, their dependencies are automatically updated too.
* Built-in debug / release build types.
* Colorful highlighting of error messages during the build.
* Support for ccache.
* Support for distcc.
* Support for building multi-platform targets.
* Support for compiler selection at build time (different versions of gcc, clang, etc.).
* Support for compiling protobuf, lex, yacc, and SWIG.
* Support for custom build rules.
* Support for running multiple tests from the command line at once.
* Support for parallel testing (multiple test processes running concurrently).
* Support for incremental testing (tests that don't need to rerun are skipped automatically).
* Integration with gperftools for automatic memory-leak detection in test programs.
* Vim syntax highlighting for build scripts.
* A git-style subcommand command-line interface.
* Support for bash command-line completion.
* Written in Python — no compilation needed, install and use directly.

It completely avoids problems such as:

* Header files were updated, but the affected modules were not rebuilt.
* A dependent library needed updating but was not updated during the build (for example, a dependency in some subdirectory was missed).

## Version History

Blade has had three major versions so far.

Blade 1 was the early version, aiming to provide a simple, easy-to-use build system; its backend was the [Scons](https://scons.org/) build system.

Blade 2 upgraded the backend to the [Ninja](https://ninja-build.org/) build system, greatly improving performance.

The latest Blade is Blade 3, which aims to be a modern build system. Blade 3 takes the project from a Linux-only, GCC-focused tool to a **three-platform, multi-toolchain** modern build system. Highlights:

* **Three platforms, one BUILD file** — Linux + macOS (clang) + Windows (MSVC), selectable per build via `cc_toolchain_config`.
* **Native [vcpkg](https://github.com/microsoft/vcpkg) integration** — version-pinned, hermetic C/C++ third-party libraries via `vcpkg#port:lib`, the `maven_jar` analog for C++.
* **Sanitizers & coverage** — `--sanitizer=address,…` (ASan/UBSan/LSan/TSan/MSan; ASan on MSVC) and `--coverage` (C/C++ / Go / Python HTML reports) on an existing target tree, no BUILD changes.
* **Profile-guided & link-time optimization** — instrumentation PGO, sample-based PGO / AutoFDO, and LTO / ThinLTO, unified across gcc / clang / MSVC / clang-cl. See [C/C++ Optimization](doc/en/optimization.md).
* **Cross-platform symbol control** — `export_map` / `linker_script` translated consistently across GCC / clang / MSVC.
* **Stronger dependency hygiene** — an `unused-deps` check and a static undefined-symbol check join the existing `missing-deps` check.
* **Modernized codebase** — Python 3.10+ only (Python 2 removed), full type annotations with pyright, comprehensive unit + cross-repo E2E tests.

See the [Upgrade to V3](doc/en/upgrade-to-v3.md) guide for details.

## Releases

Get the [latest stable release](https://github.com/blade-build/blade-build/releases/latest); the `master` branch is the active development line for Blade 3. See all [releases](https://github.com/blade-build/blade-build/releases), and the [Upgrade to V3](doc/en/upgrade-to-v3.md) guide.

For Blade 2, use the [`v2`](https://github.com/blade-build/blade-build/tree/v2) branch or the [v2.1.0 tag](https://github.com/blade-build/blade-build/releases/tag/v2.1.0); see the [V2 Upgrade Notes](doc/en/upgrade-to-v2.md).

## Documentation

* [Full Documentation](https://blade-build.github.io/docs/en/)

## Contributors

Blade was open-sourced in 2012 as one of Tencent's earliest open-source projects. It has since seen wide adoption across Tencent's technology stack — advertising platforms, WeChat backend services, game servers, and core infrastructure — and beyond Tencent, companies such as Xiaomi, Baidu, and iQiyi use Blade as well.

This has grown an active contributor community, with many Pull Requests from inside and outside the company. The project was originally hosted on Google Code; after Google Code shut down, it moved to chen3feng's personal repository for continued maintenance and evolution, and finally moved here.

[![Contributers](https://contrib.rocks/image?repo=blade-build/blade-build)](https://github.com/blade-build/blade-build/graphs/contributors)

## Star History

Even if you don't have the time or energy to contribute, stars are warmly welcome.

<a href="https://www.star-history.com/?repos=blade-build%2Fblade-build&type=date&legend=top-left">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&theme=dark&legend=top-left" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&legend=top-left" />
   <img alt="Star History Chart" src="https://api.star-history.com/chart?repos=blade-build/blade-build&type=date&legend=top-left" />
 </picture>
</a>

## Credits

* Blade is inspired by Google's public information about their build system. Here is a reference article from Google's official blog:
  [Build in the Cloud: How the Build System Works](http://google-engtools.blogspot.com/2011/08/build-in-cloud-how-build-system-works.html).
  Later, in 2015, Google released a partially rewritten version under the new name `bazel`.

* Blade generates [Ninja](https://ninja-build.org/) scripts internally to drive the build, so it depends on Ninja at runtime.
* [Python](http://www.python.org) is a simple yet powerful language, and we like it a lot.

Our philosophy: liberate programmers, improve productivity, and use tools to solve non-creative technical problems.

Welcome to Blade — we look forward to your contributions.
