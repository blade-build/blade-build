# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Pure helpers for native vcpkg support (issue #1236).

This module holds the provider-independent data extraction that the vcpkg
dependency provider builds on: deriving the vcpkg triplet from blade's resolved
toolchain, and parsing a port's pkg-config (`.pc`) file. Both are pure
functions over plain inputs (strings / os+arch tokens), unit-tested in
isolation; the `VcpkgLibrary` target and the `vcpkg#port:lib` handler that
consume them are wired up separately.

Phase 1 resolves artifacts from an install tree the user produced themselves
(`vcpkg install ...`), so `triplet_for` returns the *vanilla* vcpkg triplet a
host's default install uses. The `blade-`prefixed overlay triplets that
chainload blade's compiler belong to the orchestration phase and are added
later.
"""

import re

# blade target_arch (canonical, from `cc -dumpmachine`) / MSVC arch -> vcpkg
# architecture token.
_VCPKG_ARCH = {
    'x86_64': 'x64', 'amd64': 'x64', 'win64': 'x64', 'x64': 'x64',
    'aarch64': 'arm64', 'arm64': 'arm64',
    'i386': 'x86', 'x86': 'x86', 'win32': 'x86',
    'arm': 'arm',
}

# blade target_os -> vcpkg OS token.
_VCPKG_OS = {'linux': 'linux', 'darwin': 'osx', 'windows': 'windows'}


def triplet_for(target_os, target_arch, vendor=None, dynamic=False):
    """Derive the vcpkg triplet for blade's resolved toolchain.

    Args:
        target_os: blade `ToolChain.target_os` -- 'linux' | 'darwin' | 'windows'.
        target_arch: blade `ToolChain.target_arch` (e.g. 'x86_64', 'aarch64')
            or an MSVC arch token ('x64', 'arm64').
        vendor: compiler vendor ('gcc' | 'clang' | 'msvc'); only consulted on
            Windows to pick MinGW vs MSVC triplets.
        dynamic: True selects the shared-library triplet variant.

    Returns:
        The triplet string (e.g. 'x64-linux', 'arm64-osx', 'x64-windows-static'),
        or None if the os/arch is unsupported.

    blade links vcpkg artifacts statically by default, so on Windows -- where
    vcpkg's default triplet is dynamic -- 'auto' resolves to the `-static`
    variant. On Linux/macOS the default vcpkg triplet is already static.
    """
    arch = _VCPKG_ARCH.get(target_arch)
    os_tok = _VCPKG_OS.get(target_os)
    if arch is None or os_tok is None:
        return None
    if os_tok == 'windows':
        if vendor in ('gcc', 'clang'):
            return '%s-mingw-%s' % (arch, 'dynamic' if dynamic else 'static')
        return '%s-windows%s' % (arch, '' if dynamic else '-static')
    # linux / osx: the vanilla triplet is static; '-dynamic' for shared.
    return '%s-%s%s' % (arch, os_tok, '-dynamic' if dynamic else '')


# pkg-config grammar bits.
_PC_KEYWORDS = {
    'name', 'description', 'version', 'requires', 'requires.private',
    'libs', 'libs.private', 'cflags', 'cflags.private', 'conflicts',
    'provides', 'url',
}
_PC_KEYWORD_RE = re.compile(r'^([A-Za-z][\w.]*)\s*:\s*(.*)$')
_PC_VAR_RE = re.compile(r'^([A-Za-z_][\w.]*)\s*=\s*(.*)$')
_PC_REF_RE = re.compile(r'\$\{([A-Za-z_][\w.]*)\}')
_PC_VERSION_OPS = {'>=', '<=', '=', '==', '>', '<', '!='}


def _expand(value, variables):
    """Expand ${var} references using the variables seen so far."""
    def repl(m):
        return variables.get(m.group(1), '')
    # A couple of passes resolve nested ${a}=${b} chains in practice.
    for _ in range(8):
        new = _PC_REF_RE.sub(repl, value)
        if new == value:
            break
        value = new
    return value


def _parse_module_list(value):
    """Extract module names from a Requires[.private] value.

    Drops version constraints, e.g. 'libssl >= 3.0, libcrypto' -> ['libssl',
    'libcrypto']. Handles comma- and/or space-separated forms.
    """
    mods = []
    skip_version = False
    for tok in re.split(r'[\s,]+', value.strip()):
        if not tok:
            continue
        if tok in _PC_VERSION_OPS:
            skip_version = True
            continue
        if skip_version:
            skip_version = False
            continue
        mods.append(tok)
    return mods


def _extract_l_libs(tokens):
    """Pull bare library names from `-lfoo` tokens (also `-l foo`)."""
    libs = []
    want_name = False
    for tok in tokens:
        if want_name:
            libs.append(tok)
            want_name = False
        elif tok == '-l':
            want_name = True
        elif tok.startswith('-l'):
            libs.append(tok[2:])
    return libs


def parse_pkgconfig(text):
    """Parse pkg-config (`.pc`) content into a structured dict.

    Returns a dict with:
        name, version              -- strings ('' if absent)
        requires, requires_private -- module-name lists (versions stripped)
        libs, libs_private, cflags -- token lists (variables expanded)
        l_libs, l_private          -- bare `-l` names from libs / libs_private

    Variable definitions (`libdir=${prefix}/lib`) are expanded; a leading
    keyword (`Libs:`) is distinguished from a variable by the fixed pkg-config
    keyword set, so a value containing '=' is not mistaken for a definition.
    """
    variables = {}
    fields = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        km = _PC_KEYWORD_RE.match(line)
        if km and km.group(1).lower() in _PC_KEYWORDS:
            fields[km.group(1).lower()] = _expand(km.group(2).strip(), variables)
            continue
        vm = _PC_VAR_RE.match(line)
        if vm:
            variables[vm.group(1)] = _expand(vm.group(2).strip(), variables)

    def tokens(key):
        v = fields.get(key, '')
        return v.split() if v else []

    libs = tokens('libs')
    libs_private = tokens('libs.private')
    return {
        'name': fields.get('name', ''),
        'version': fields.get('version', ''),
        'requires': _parse_module_list(fields.get('requires', '')),
        'requires_private': _parse_module_list(fields.get('requires.private', '')),
        'libs': libs,
        'libs_private': libs_private,
        'cflags': tokens('cflags'),
        'l_libs': _extract_l_libs(libs),
        'l_private': _extract_l_libs(libs_private),
    }
