# Copyright (c) 2016 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   July 12, 2016

"""
Implement go_library, go_binary and go_test, plus the go_package wrapper.

Go modules only (GOPATH mode is not supported). Compilation is delegated to the
`go` toolchain; Blade owns the dependency graph and ordering:

  * go_binary   -- built from its declared srcs in **file mode**
                   (`go build <srcs...>`), so a directory with multiple `main`
                   files can be split into separate binaries.
  * go_test     -- `go test -c` over its package directory.
  * go_library  -- package-scoped **compile-check** (`go build <pkg>`); it has
                   no linkable artifact (the Go build cache replaced the GOPATH
                   archive), only a stamp file. It exists as a dependency-graph
                   node (ordering / visibility) and an early per-package check;
                   consumers take the stamp as an order-only dep and let `go`
                   recompile the package (a build-cache hit).

Each target is compiled in the context of its owning module -- the nearest
`go.mod` at or above the target's directory -- via `go -C <module_dir>`.
"""


import os
import re

from blade import build_manager
from blade import build_rules
from blade import config
from blade import console
from blade import rule_registry
from blade.blade_types import StrOrListOpt
from blade.ninja_rule import NinjaRule
from blade.target import Target
from blade.util import to_unix_path, var_to_list, var_to_list_or_none


_package_re = re.compile(r'^\s*package\s+(\w+)\s*$')


def _find_module_dir(start):
    """Find the owning module directory: the nearest ancestor of `start`
    (a workspace-relative dir, '' == workspace root) that contains a `go.mod`.

    Existence is checked relative to the current directory, which is the
    workspace root during target analysis. Returns the workspace-relative module
    directory ('' for the root module) or None if no `go.mod` is found.
    """
    cur = start
    while True:
        gomod = os.path.join(cur, 'go.mod') if cur else 'go.mod'
        if os.path.exists(gomod):
            return cur
        if not cur:
            return None
        cur = os.path.dirname(cur)


class GoTarget(Target):
    """Base of all go targets."""

    def __init__(self,
                 name: str | None,
                 type: str,
                 srcs: StrOrListOpt,
                 deps: StrOrListOpt,
                 extra_goflags: StrOrListOpt,
                 visibility: StrOrListOpt,
                 tags: StrOrListOpt,
                 kwargs: dict[str, object]):
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        visibility = var_to_list_or_none(visibility)
        extra_goflags = ' '.join(var_to_list(extra_goflags))

        super().__init__(
                name=name,
                type=type,
                srcs=srcs,
                src_exts=['go'],
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)

        self.attr['extra_goflags'] = extra_goflags
        self._add_tags('lang:go')
        self._resolve_module()

    def _resolve_module(self):
        """Locate the owning Go module and compute module-relative paths.

        Go sources of one package must share a directory; the module is the
        nearest `go.mod` at or above it.
        """
        srcs = [self._source_file_path(s) for s in self.srcs]
        dirs = {os.path.dirname(s) for s in srcs}
        if len(dirs) != 1:
            self.error('Go sources of the same target must be in the same '
                       'directory. Sources: %s' % ', '.join(self.srcs))
            self._module_dir = '.'
            self._pkg = '.'
            return
        module_dir = _find_module_dir(self.path)
        if module_dir is None:
            self.error(
                'No go.mod found at or above "%s". Blade builds Go in module '
                'mode only; add a go.mod at the module root.' % (self.path or '.'))
            module_dir = ''
        # `-C` dir and paths back into the module, all workspace-relative
        # (ninja/analysis run from the workspace root).
        self._module_dir = module_dir or '.'
        pkg_rel = os.path.relpath(self.path or '.', module_dir or '.')
        self._pkg = '.' if pkg_rel == '.' else './' + pkg_rel
        # module-relative source files, for file-mode `go build`
        self._go_files = ' '.join(
            os.path.relpath(s, module_dir or '.') for s in srcs)
        # go.mod / go.sum as build inputs (workspace-relative)
        self._module_files = []
        for f in ('go.mod', 'go.sum'):
            p = os.path.join(module_dir, f) if module_dir else f
            if os.path.exists(p):
                self._module_files.append(p)

    def _expand_deps_generation(self):
        build_targets = self.blade.get_build_targets()
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for dep in self.expanded_deps:
            build_targets[dep].attr['generate_go'] = True

    def _go_implicit_deps(self):
        """Ninja implicit deps: own srcs, module files, and dep outputs.

        Depending on a dep's output (a go_library stamp, or a proto_library's
        generated `.pb.go` files) gives both ordering and stamp-chain
        incrementality without declaring Go->Go imports by hand.
        """
        targets = self.blade.get_build_targets()
        deps = list(self._module_files)
        deps += [self._source_file_path(s) for s in self.srcs]
        for key in self.deps:
            path = targets[key]._get_target_file('gopkg')
            if path:
                deps += var_to_list(path)
        return deps

    def _go_variables(self):
        return {
            'module_dir': self._module_dir,
            'package': self._pkg,
            'gofiles': self._go_files,
            'extra_goflags': self.attr['extra_goflags'],
        }

    def _transitive_go_pb(self):
        """All generated `.pb.go` files reachable through deps (build_dir paths).

        `go build` compiles the whole import closure, so a binary/test needs the
        overlay to cover proto-generated Go anywhere beneath it, not just direct
        deps.
        """
        targets = self.blade.get_build_targets()
        files = []
        assert self.expanded_deps is not None, 'expanded_deps not expanded'
        for key in self.expanded_deps:
            pb = targets[key]._get_target_file('go_pb')
            if pb:
                files += var_to_list(pb)
        return list(dict.fromkeys(files))  # de-dup, keep order

    def generate(self):
        output = self._target_file_path(self.name)
        implicit_deps = self._go_implicit_deps()
        variables = self._go_variables()
        # Overlay for proto-generated Go (under build_dir): map each `.pb.go` to
        # its in-module location so `go build` resolves it without an in-tree copy.
        pb_files = self._transitive_go_pb()
        if pb_files:
            overlay = self._target_file_path(self.name + '.overlay.json')
            self.generate_build('gooverlay', overlay, inputs=pb_files,
                                variables={'build_dir': to_unix_path(self.build_dir)})
            implicit_deps = implicit_deps + [overlay]
            variables['goverlay'] = '-overlay $$PWD/%s' % to_unix_path(overlay)
        else:
            variables['goverlay'] = ''
        self.generate_build(self.attr['go_rule'], output,
                            implicit_deps=implicit_deps, variables=variables)
        label = self.attr.get('go_label')
        if label:
            self._add_target_file(label, output)


class GoLibrary(GoTarget):
    """A Go package built as a compile-check (no artifact, just a stamp)."""

    def __init__(self, name, srcs, deps, visibility, tags, extra_goflags, kwargs):
        super().__init__(
                name=name, type='go_library', srcs=srcs, deps=deps,
                visibility=visibility, tags=tags, extra_goflags=extra_goflags,
                kwargs=kwargs)
        self.attr['go_rule'] = 'golibrary'
        self.attr['go_label'] = 'gopkg'
        self._add_tags('type:library')


class GoBinary(GoTarget):
    """A Go executable, built from its srcs in file mode."""

    def __init__(self, name, srcs, deps, visibility, tags, extra_goflags, kwargs):
        super().__init__(
                name=name, type='go_binary', srcs=srcs, deps=deps,
                visibility=visibility, tags=tags, extra_goflags=extra_goflags,
                kwargs=kwargs)
        self.attr['go_rule'] = 'gobinary'
        self.attr['go_label'] = 'bin'
        self._add_tags('type:binary')


class GoTest(GoTarget):
    """A Go test binary, built with `go test -c` over its package."""

    def __init__(self, name, srcs, deps, visibility, tags, testdata, extra_goflags, kwargs):
        super().__init__(
                name=name, type='go_test', srcs=srcs, deps=deps,
                visibility=visibility, tags=tags, extra_goflags=extra_goflags,
                kwargs=kwargs)
        self.attr['go_rule'] = 'gotest'
        self.attr['testdata'] = var_to_list(testdata)
        self._add_tags('type:test')


def go_library(name, srcs, deps=None, extra_goflags=None, visibility=None,
               tags=None, **kwargs):
    build_manager.instance.register_target(GoLibrary(
        name=name, srcs=srcs, deps=deps, visibility=visibility, tags=tags,
        extra_goflags=extra_goflags, kwargs=kwargs))


def go_binary(name, srcs, deps=None, visibility=None, tags=None,
              extra_goflags=None, **kwargs):
    build_manager.instance.register_target(GoBinary(
        name=name, srcs=srcs, deps=deps, extra_goflags=extra_goflags,
        visibility=visibility, tags=tags, kwargs=kwargs))


def go_test(name, srcs, deps=None, visibility=None, tags=None, testdata=None,
            extra_goflags=None, **kwargs):
    build_manager.instance.register_target(GoTest(
        name=name, srcs=srcs, deps=deps, visibility=visibility, tags=tags,
        testdata=testdata, extra_goflags=extra_goflags, kwargs=kwargs))


def find_go_srcs(path):
    srcs, tests = [], []
    for name in os.listdir(path):
        if name.startswith('.') or not name.endswith('.go'):
            continue
        if os.path.isfile(os.path.join(path, name)):
            if name.endswith('_test.go'):
                tests.append(name)
            else:
                srcs.append(name)
    return srcs, tests


def extract_go_package(path):
    with open(path) as f:
        for line in f:
            m = _package_re.match(line)
            if m:
                return m.group(1)
    raise Exception('Failed to find package in %s' % path)


def go_package(name, deps=None, testdata=None, visibility=None, extra_goflags=None):
    path = build_manager.instance.get_current_source_path()
    srcs, tests = find_go_srcs(path)
    if not srcs and not tests:
        console.error('Empty go sources in %s' % path)
        return
    if srcs:
        main = any(extract_go_package(os.path.join(path, src)) == 'main'
                   for src in srcs)
        if main:
            go_binary(name=name, srcs=srcs, deps=deps, visibility=visibility,
                      extra_goflags=extra_goflags)
        else:
            go_library(name=name, srcs=srcs, deps=deps, visibility=visibility,
                       extra_goflags=extra_goflags)
    if tests:
        go_test(name='%s_test' % name, srcs=tests, deps=deps,
                visibility=visibility, testdata=testdata,
                extra_goflags=extra_goflags)


build_rules.register_function(go_library)
build_rules.register_function(go_binary)
build_rules.register_function(go_test)
build_rules.register_function(go_package)


def _generate_go_rules(ctx):
    """Ninja rules for go_library / go_binary / go_test (modules only).

    No-op unless `go` is configured. Each rule compiles in the target's module
    via `go -C ${module_dir}`; outputs are written with an absolute path
    (`$PWD/${out}`) since `-C` also reinterprets `-o`. No serialization pool --
    the Go build cache is concurrency-safe.
    """
    go = config.get_item('go_config', 'go')
    if not go:
        return
    go_home = config.get_item('go_config', 'go_home')
    goenv = 'GOPATH=%s ' % os.path.abspath(go_home) if go_home else ''
    gocover = ' -cover -covermode=count' if getattr(ctx.options, 'coverage', False) else ''

    ctx.emit_rule(NinjaRule(
        name='golibrary',
        command=f'{goenv}{go} -C ${{module_dir}} build ${{goverlay}} ${{extra_goflags}} '
                f'${{package}} && touch ${{out}}',
        description='GO BUILD ${package}'))
    ctx.emit_rule(NinjaRule(
        name='gobinary',
        command=f'{goenv}{go} -C ${{module_dir}} build ${{goverlay}} ${{extra_goflags}} '
                f'-o $$PWD/${{out}} ${{gofiles}}',
        description='GO LINK ${out}'))
    ctx.emit_rule(NinjaRule(
        name='gotest',
        command=f'{goenv}{go} -C ${{module_dir}} test -c{gocover} ${{goverlay}} '
                f'${{extra_goflags}} -o $$PWD/${{out}} ${{package}}',
        description='GO TEST ${package}'))
    # Writes the `go build -overlay` JSON that exposes build_dir-generated Go
    # (proto .pb.go) at its in-module location; see builtin_tools.go_overlay.
    ctx.emit_rule(NinjaRule(
        name='gooverlay',
        command=ctx.builtin_command('go_overlay', '--out=${out} --build_dir=${build_dir} ${in}'),
        description='GO OVERLAY ${out}'))


rule_registry.register_rule_provider(
    _generate_go_rules, order=rule_registry.ORDER_GO, name='go')
