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

import os
import re

from blade import target as _blade_target

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


# --- Phase 2 orchestration inputs: synthetic manifest + overlay triplet ------
#
# When blade drives `vcpkg install` itself, it generates a manifest from the
# vcpkg_config whitelist and an overlay triplet that chainloads blade's resolved
# compiler, so vcpkg's artifacts stay ABI-compatible with the rest of the build.
# These are pure generators over plain inputs; writing the files + invoking
# vcpkg is wired separately.

def overlay_triplet_name(triplet):
    """The blade overlay triplet name for a vanilla vcpkg triplet."""
    return 'blade-' + triplet


def shared_overlay_triplet_name(triplet):
    """The overlay triplet that force-builds 'auto' ports as shared libraries.

    A separate triplet (and install subtree) is needed because vcpkg builds a
    single linkage per triplet: the main `blade-<triplet>` tree holds the
    static .a, and `blade-<triplet>-shared` holds the on-demand .dylib/.so."""
    return overlay_triplet_name(triplet) + '-shared'


def manifest_json(packages, baseline=''):
    """Build the synthetic vcpkg.json manifest from vcpkg_config (issue #1236).

    A bare version -> a dependency + an `overrides` pin; a dict with features ->
    a dependency object carrying them. Maps vcpkg_config 1:1 onto vcpkg's
    manifest model (one version / feature set per package per workspace).
    """
    dependencies = []
    overrides = []
    for port in sorted(packages):
        spec = packages[port]
        if isinstance(spec, str):
            version, features = spec, None
        else:
            version, features = spec.get('version'), spec.get('features')
        if features:
            dependencies.append({'name': port, 'features': list(features)})
        else:
            dependencies.append(port)
        if version:
            overrides.append({'name': port, 'version': version})
    manifest: dict = {'dependencies': dependencies}
    if baseline:
        manifest['builtin-baseline'] = baseline
    if overrides:
        manifest['overrides'] = overrides
    return manifest


def configuration_json(registries):
    """Build vcpkg-configuration.json for private registries, or None."""
    if not registries:
        return None
    return {'registries': [dict(r) for r in registries]}


def chainload_cmake(cc, cxx, c_flags='', cxx_flags=''):
    """CMake toolchain file pinning vcpkg's compiler to blade's resolved one."""
    # CMake parses backslashes in a string as escapes, so a Windows compiler
    # path (C:\...\cl.exe) must use forward slashes (CMake accepts them on
    # Windows). Without this the chainload file is a CMake syntax error and every
    # vcpkg port configure fails ("Invalid character escape").
    cc = cc.replace('\\', '/')
    cxx = cxx.replace('\\', '/')
    return (
        'set(CMAKE_C_COMPILER "%s")\n'
        'set(CMAKE_CXX_COMPILER "%s")\n'
        'set(CMAKE_C_FLAGS_INIT "%s")\n'
        'set(CMAKE_CXX_FLAGS_INIT "%s")\n' % (cc, cxx, c_flags, cxx_flags))


# Overlay triplet target-OS settings, mirroring vcpkg's stock triplets. Linux
# and osx set VCPKG_CMAKE_SYSTEM_NAME (which is how vcpkg derives
# VCPKG_TARGET_IS_LINUX / _OSX -- ports branch on it; openssl uses the Windows
# portfile without it). On macOS that name is the *native* system, not a cross
# build. Windows omits it (it is vcpkg's default host). osx also pins
# VCPKG_OSX_ARCHITECTURES to the Apple arch name.
_VCPKG_SYSTEM_NAME = {'linux': 'Linux', 'darwin': 'Darwin'}
_VCPKG_OSX_ARCH = {'x64': 'x86_64', 'arm64': 'arm64', 'x86': 'i386'}


def port_options(packages, port):
    """Per-port (linkage, link_all_symbols, include_prefix) from the spec.

    A bare version string -> defaults ('static', False, None). A dict spec may
    carry `linkage`, `link_all_symbols` (bool) and `include_prefix` (str: expose
    vcpkg's include dir under this subdir, for libs flare includes as
    "<prefix>/<header>" but vcpkg ships at include top).

    `linkage` is one of:
      'static'  (default) -- only the static archive (.a) is built.
      'dynamic'           -- only the shared library (.dylib/.so) is built; both
                             link modes share that single instance.
      'auto'              -- the static archive is always built; the shared
                             library is built *on demand*, only when a
                             dynamic_link binary actually depends on the port
                             (mirrors cc_library's generate_dynamic). This gives
                             a static-link tool a self-contained .a while a
                             dynamic-link binary still shares one .dylib.
    """
    spec = packages.get(port)
    if isinstance(spec, dict):
        return (spec.get('linkage') or 'static',
                bool(spec.get('link_all_symbols')),
                spec.get('include_prefix') or None)
    return 'static', False, None


def dynamic_ports(packages):
    """Ports whose spec requests linkage='dynamic' (sorted, deterministic).

    These build their shared library in the *main* install tree. 'auto' ports
    are excluded here: they build static in the main tree and their shared lib
    lands in the separate `-shared` tree (see auto_ports / setup)."""
    return sorted(p for p, s in packages.items()
                  if isinstance(s, dict) and s.get('linkage') == 'dynamic')


def auto_ports(packages):
    """Ports whose spec requests linkage='auto' (sorted, deterministic)."""
    return sorted(p for p, s in packages.items()
                  if isinstance(s, dict) and s.get('linkage') == 'auto')


def port_cmake_options(packages):
    """{port: [cmake_options]} for ports that request extra configure options."""
    return {p: s['cmake_options'] for p, s in packages.items()
            if isinstance(s, dict) and s.get('cmake_options')}


def is_msvc_abi_triplet(triplet: str | None) -> bool:
    """True for vcpkg triplets that use the MSVC CRT + MSVC STL -- the
    `*-windows*` family (cl.exe and clang-cl both target it). MinGW is
    `*-mingw-*` (libstdc++, no debug/release ABI split) and is excluded.

    Gate on the triplet, not the compiler name: blade classifies clang-cl as
    'clang', so a `cc_is('msvc')` gate would miss it -- but its triplet is still
    `*-windows*`."""
    return '-windows' in (triplet or '')


def vcpkg_build_type(triplet: str | None, profile: str) -> str | None:
    """The `VCPKG_BUILD_TYPE` for an overlay triplet, or None to build both.

    blade only links the release tree, so default to release-only (half the
    install time/disk). The exception is an MSVC-ABI **debug** build: debug and
    release are ABI-incompatible there -- the CRT differs (`/MDd` ucrtbased vs
    `/MD` ucrtbase) and MSVC STL's `_ITERATOR_DEBUG_LEVEL` changes `std::`
    container layout -- so a debug MSVC/clang-cl program must link debug libs.
    For that case return None: build BOTH (the debug tree is needed, and headers
    only ship with the release install, so a debug-only build would lose them).
    clang/gcc/MinGW are unaffected (release libs work in debug)."""
    if profile == 'debug' and is_msvc_abi_triplet(triplet):
        return None
    return 'release'


def lib_subdir(triplet: str | None, profile: str) -> str:
    """The install-tree lib subdir to link from: `debug/lib` for an MSVC-ABI
    debug build (matching vcpkg_build_type building both), else `lib`."""
    if profile == 'debug' and is_msvc_abi_triplet(triplet):
        return os.path.join('debug', 'lib')
    return 'lib'


def overlay_triplet_cmake(target_os, target_arch, library_linkage='static',
                          dynamic_ports=(), cmake_options=None,
                          build_type: str | None = 'release', chainload=True,
                          chainload_rel='../blade-chainload.cmake'):
    """The overlay triplet `.cmake` for a vanilla vcpkg triplet.

    Mirrors vcpkg's stock triplet for the OS (so ports detect the target
    correctly). `library_linkage` is the default ('static'); ports in
    `dynamic_ports` are overridden to dynamic, and `cmake_options` ({port:
    [opts]}) sets per-port VCPKG_CMAKE_CONFIGURE_OPTIONS. vcpkg re-evaluates the
    triplet per port, so `if(PORT ...)` guards give per-port behavior. Returns
    None if os/arch is unsupported.

    `chainload` adds the chainload toolchain that pins blade's compiler -- used
    for gcc/clang/MinGW. For MSVC (cl.exe) it is False: a chainload would put
    vcpkg in `external` toolset mode and make it SKIP its MSVC environment setup,
    so CMake never gets mt.exe/rc.exe/INCLUDE/LIB and every port fails to link.
    Letting vcpkg use its native MSVC support sets all of that up correctly.
    """
    arch = _VCPKG_ARCH.get(target_arch)
    if arch is None or target_os not in _VCPKG_OS:
        return None
    lines = [
        'set(VCPKG_TARGET_ARCHITECTURE %s)' % arch,
        'set(VCPKG_CRT_LINKAGE dynamic)',
        'set(VCPKG_LIBRARY_LINKAGE %s)' % library_linkage,
    ]
    # vcpkg builds both release and debug by default; blade only links the
    # release tree, so default to release-only (half the install time/disk).
    # build_type=None means build both -- needed for an MSVC-ABI debug build,
    # whose ABI-incompatible debug libs must be linked (see vcpkg_build_type).
    if build_type:
        lines.append('set(VCPKG_BUILD_TYPE %s)' % build_type)
    if target_os != 'windows':
        # Match blade's compile-once-with-fPIC model: a static vcpkg .a may be
        # linked into a .so (a generate_dynamic / dynamic_link consumer), which
        # on ELF requires position-independent code. vcpkg static libs are NOT
        # -fPIC by default -> "relocation ... can not be used when making a
        # shared object; recompile with -fPIC". No-op on macOS (always PIC);
        # -fPIC is unknown to MSVC and ignored-with-a-warning by MinGW, so skip
        # Windows. VCPKG_C/CXX_FLAGS reach both CMake and autotools/make ports.
        lines.append('set(VCPKG_C_FLAGS "-fPIC")')
        lines.append('set(VCPKG_CXX_FLAGS "-fPIC")')
    for port in dynamic_ports:
        lines.append('if(PORT STREQUAL "%s")' % port)
        lines.append('    set(VCPKG_LIBRARY_LINKAGE dynamic)')
        lines.append('endif()')
    for port, opts in sorted((cmake_options or {}).items()):
        lines.append('if(PORT STREQUAL "%s")' % port)
        lines.append('    set(VCPKG_CMAKE_CONFIGURE_OPTIONS %s)'
                     % ' '.join('"%s"' % o for o in opts))
        lines.append('endif()')
    system = _VCPKG_SYSTEM_NAME.get(target_os)
    if system:
        lines.append('set(VCPKG_CMAKE_SYSTEM_NAME %s)' % system)
    if target_os == 'darwin':
        lines.append('set(VCPKG_OSX_ARCHITECTURES %s)'
                     % _VCPKG_OSX_ARCH.get(arch, arch))
    if chainload:
        lines.append('set(VCPKG_CHAINLOAD_TOOLCHAIN_FILE '
                     '${CMAKE_CURRENT_LIST_DIR}/%s)' % chainload_rel)
    return '\n'.join(lines) + '\n'


def install_location(cfg, vanilla_triplet, build_dir):
    """Return (artifacts_root, triplet) for resolving a `vcpkg#...` reference.

    manage=True (default): the blade-managed hermetic tree under the build dir,
    with the overlay triplet `blade-<vanilla>`. manage=False: the tree the user
    installed themselves (vcpkg_config.root or $VCPKG_ROOT) with the vanilla
    triplet. `installed/<triplet>/` is appended by resolve_reference.
    """
    if cfg.get('manage', True):
        root = os.path.join(build_dir, cfg.get('install_dir') or '.cache/vcpkg')
        triplet = overlay_triplet_name(vanilla_triplet)
    else:
        root = cfg.get('root') or os.environ.get('VCPKG_ROOT', '')
        triplet = vanilla_triplet
    # Absolute so the resolved include dir survives _incs_to_fullpath (which
    # would otherwise prepend the target's path sentinel to a relative dir) and
    # so the .a path is independent of the compiler's working directory. blade
    # has chdir'd to the workspace root, so abspath resolves against it.
    if root:
        root = os.path.abspath(root)
    return root, triplet


class VcpkgError(Exception):
    """A `vcpkg#...` reference could not be resolved (issue #1236)."""


def resolve_reference(coordinate, packages, root, triplet, profile: str = 'release'):
    """Resolve a `vcpkg#<coordinate>` reference to install-tree locations.

    Pure validation + path computation (no toolchain / Target / filesystem):
    the handler derives `triplet`/`root`/`profile` from the toolchain + config
    and passes them in. Raises VcpkgError (with a user-facing message) on any
    problem.

    An MSVC-ABI debug build links the `debug/lib` subtree (its debug CRT/STL is
    ABI-incompatible with release); every other case links `lib`. The include
    dir is shared (vcpkg installs headers once, with the release build).

    Returns a dict: port, lib, key, header_only, lib_dir, include_dir.
    """
    if ':' not in coordinate:
        raise VcpkgError(
            'invalid dependency "vcpkg#%s": a port must name a library, e.g. '
            '"vcpkg#%s:<lib>" (or "vcpkg#%s:hdrs" for a header-only port)'
            % (coordinate, coordinate, coordinate))
    port, lib = coordinate.split(':', 1)
    if not port or not lib:
        raise VcpkgError('invalid dependency "vcpkg#%s": expected "<port>:<lib>"'
                         % coordinate)
    # Strict by default: the workspace whitelist is the single source of truth
    # for which ports may be referenced.
    if port not in packages:
        raise VcpkgError(
            'vcpkg port "%s" is not in the vcpkg_config.packages whitelist; '
            'declare it in BLADE_ROOT, e.g. '
            'vcpkg_config(packages={"%s": "<version>"})' % (port, port))
    if not root:
        raise VcpkgError(
            'vcpkg: no install root for "vcpkg#%s"; set vcpkg_config(root=...) '
            'or the VCPKG_ROOT environment variable' % coordinate)
    if not triplet:
        raise VcpkgError(
            'vcpkg: could not determine a triplet for "vcpkg#%s"; set '
            'vcpkg_config(triplet=...)' % coordinate)
    installed = os.path.join(root, 'installed', triplet)
    return {
        'port': port,
        'lib': lib,
        'key': 'vcpkg#%s:%s' % (port, lib),
        'header_only': lib == 'hdrs',
        'lib_dir': os.path.join(installed, lib_subdir(triplet, profile)),
        'include_dir': os.path.join(installed, 'include'),
    }


def triplet_for_toolchain(toolchain, dynamic=False):
    """Derive the vcpkg triplet from a blade ToolChain instance."""
    vendor = next((v for v in ('gcc', 'clang', 'msvc') if toolchain.cc_is(v)), None)
    return triplet_for(toolchain.target_os, toolchain.target_arch, vendor, dynamic)


def _path_under(path, prefixes):
    """True if workspace-relative `path` is within one of `prefixes` (each may
    be written `dir` or `//dir`)."""
    for prefix in prefixes:
        prefix = prefix.strip('/')
        if path == prefix or path.startswith(prefix + '/'):
            return True
    return False


def _vcpkg_dep_handler(referrer, coordinate):
    """`<scheme>#...` provider for vcpkg (registered below).

    Resolves the reference against the workspace whitelist + install tree and
    auto-creates a VcpkgLibrary target (like _add_system_library), returning its
    database key. Reports via referrer.error() and returns None on failure.
    """
    from blade import config
    cfg = config.get_section('vcpkg_config')
    allowed = cfg.get('direct_use_allowed') or []
    if allowed and not _path_under(referrer.path, allowed):
        referrer.error(
            'vcpkg#%s: direct vcpkg# references are restricted to %s '
            '(vcpkg_config.direct_use_allowed); route this dependency through a '
            'wrapper cc_library there' % (
                coordinate, ', '.join('//%s' % a.strip('/') for a in allowed)))
        return None
    toolchain = referrer.blade.get_build_toolchain()
    vanilla = cfg.get('triplet')
    if not vanilla or vanilla == 'auto':
        vanilla = triplet_for_toolchain(toolchain)
    root, triplet = install_location(cfg, vanilla, referrer.blade.get_build_dir())
    profile = referrer.blade.get_options().profile
    packages = cfg.get('packages', {})
    try:
        info = resolve_reference(coordinate, packages, root, triplet, profile)
    except VcpkgError as e:
        referrer.error(str(e))
        return None
    key = info['key']
    if key in referrer.target_database:
        return key
    linkage, link_all_symbols, include_prefix = port_options(packages, info['port'])
    # For an 'auto' port the shared library lives in the separate `-shared`
    # install tree (managed mode); a 'dynamic' port's .dylib is in the main tree
    # alongside its lib_dir. install_location built `triplet` from the same cfg,
    # so deriving the shared sibling here keeps the path computation co-located.
    if linkage == 'auto' and cfg.get('manage', True):
        shared_triplet = shared_overlay_triplet_name(vanilla)
        dynamic_lib_dir = os.path.join(
            shared_install_root(root), shared_triplet,
            lib_subdir(shared_triplet, profile))
    else:
        dynamic_lib_dir = info['lib_dir']
    # Lazy import: cc_targets is loaded before this module, but keeping the
    # import local avoids a hard module-level cycle (cc_targets -> ... -> here).
    from blade.cc_targets import VcpkgLibrary
    target = VcpkgLibrary(info['port'], info['lib'], key,
                          info['lib_dir'], info['include_dir'], info['header_only'],
                          linkage=linkage, dynamic_lib_dir=dynamic_lib_dir,
                          link_all_symbols=link_all_symbols,
                          include_prefix=include_prefix)
    referrer.blade.register_target(target)
    return key


def _find_vcpkg_tool(cfg):
    """Locate the vcpkg executable: vcpkg_config.root / $VCPKG_ROOT / PATH."""
    import shutil
    tool_root = cfg.get('root') or os.environ.get('VCPKG_ROOT', '')
    if tool_root:
        # The executable is `vcpkg.exe` on Windows, `vcpkg` elsewhere.
        for name in ('vcpkg.exe', 'vcpkg') if os.name == 'nt' else ('vcpkg',):
            candidate = os.path.join(tool_root, name)
            if os.path.exists(candidate):
                return candidate
    return shutil.which('vcpkg')


def setup(builder):
    """Phase 2: blade-managed `vcpkg install` (issue #1236).

    Runs once, after config load and before BUILD files are parsed, so the
    installed artifacts exist on disk by the time VcpkgLibrary targets resolve.
    A no-op unless vcpkg_config(manage=True) (the default) with a non-empty
    packages whitelist. Returns True on success or no-op, False on failure
    (after reporting). An MD5 stamp over the generated inputs skips the install
    when nothing relevant changed.
    """
    import hashlib
    import json
    from blade import config, console, util
    cfg = config.get_section('vcpkg_config')
    packages = cfg.get('packages') or {}
    if not cfg.get('manage', True) or not packages:
        return True
    # Demand-driven: only install when the build actually references a vcpkg
    # package. This lets a workspace declare vcpkg_config unconditionally (its
    # use of vcpkg is a fixed project property) without forcing every build --
    # or every consumer of an unrelated target -- to need the vcpkg tool or pay
    # the install. A build with no `vcpkg#...` dependency is a no-op here.
    if not _build_uses_vcpkg(builder):
        return True

    toolchain = builder.get_build_toolchain()
    vanilla = cfg.get('triplet')
    if not vanilla or vanilla == 'auto':
        vanilla = triplet_for_toolchain(toolchain)
    profile = builder.get_options().profile
    # MSVC (cl.exe) uses vcpkg's native toolchain (no chainload) so vcpkg sets up
    # the full MSVC environment; gcc/clang/MinGW are chainloaded to pin blade's
    # compiler.
    chainload = not toolchain.cc_is('msvc')
    triplet_cmake = (overlay_triplet_cmake(
        toolchain.target_os, toolchain.target_arch,
        dynamic_ports=dynamic_ports(packages),
        cmake_options=port_cmake_options(packages),
        build_type=vcpkg_build_type(vanilla, profile),
        chainload=chainload) if vanilla else None)
    if not vanilla or triplet_cmake is None:
        console.error('vcpkg: cannot derive a triplet for os=%s arch=%s; set '
                      'vcpkg_config(triplet=...)'
                      % (toolchain.target_os, toolchain.target_arch))
        return False
    overlay = overlay_triplet_name(vanilla)

    base = os.path.join(builder.get_build_dir(), cfg.get('install_dir') or '.cache/vcpkg')
    triplets_dir = os.path.join(base, 'triplets')
    installed_root = os.path.join(base, 'installed')
    os.makedirs(triplets_dir, exist_ok=True)

    manifest = json.dumps(manifest_json(packages, cfg.get('baseline', '')),
                          indent=2, sort_keys=True)
    chainload = chainload_cmake(toolchain.tool('cc') or 'cc',
                                toolchain.tool('cxx') or 'c++')
    files = {
        os.path.join(base, 'vcpkg.json'): manifest,
        os.path.join(base, 'blade-chainload.cmake'): chainload,
        os.path.join(triplets_dir, overlay + '.cmake'): triplet_cmake,
    }
    configuration = configuration_json(cfg.get('registries') or [])
    if configuration is not None:
        files[os.path.join(base, 'vcpkg-configuration.json')] = json.dumps(
            configuration, indent=2, sort_keys=True)
    for path, content in files.items():
        util.write_if_changed(path, content)

    stamp = hashlib.md5(
        (manifest + chainload + triplet_cmake + overlay).encode()).hexdigest()
    stamp_file = os.path.join(base, '.blade-vcpkg-stamp')
    main_fresh = (os.path.isdir(os.path.join(installed_root, overlay))
                  and os.path.exists(stamp_file)
                  and _read_text(stamp_file).strip() == stamp)

    # The 'auto' ports a dynamic_link binary actually depends on (computed from
    # the analyzed graph -- setup() runs in build(), after analyze) determine
    # whether the second, shared install is needed at all.
    demanded = _auto_dynamic_ports(builder, packages)

    if main_fresh and not demanded:
        return True

    vcpkg_bin = _find_vcpkg_tool(cfg)
    if vcpkg_bin is None:
        console.error('vcpkg: the vcpkg tool was not found; set '
                      'vcpkg_config(root=...), $VCPKG_ROOT, or put vcpkg on PATH')
        return False

    if not main_fresh:
        cmd = [vcpkg_bin, 'install',
               '--triplet', overlay,
               '--x-manifest-root', base,
               '--x-install-root', installed_root,
               '--overlay-triplets', triplets_dir]
        # Binary cache: 'auto' leaves vcpkg's default local cache on; any other
        # value is a vcpkg binarysource string (files / nuget / GitHub /
        # x-azblob / x-gcs / ...), reused across runs.
        binary_cache = cfg.get('binary_cache') or 'auto'
        if binary_cache != 'auto':
            cmd.append('--binarysource=' + binary_cache)
        console.info('vcpkg: installing %d package(s) for %s ...'
                     % (len(packages), overlay))
        if not _run_install_with_progress(cmd):
            return False
        with open(stamp_file, 'w') as f:
            f.write(stamp)

    # Second tree: build the demanded 'auto' ports as shared libraries. Skipped
    # entirely when nothing dynamic-links an 'auto' port (e.g. an all-static
    # debug build).
    if demanded and not _install_shared(
            vcpkg_bin, cfg, vanilla, demanded, packages,
            base, triplets_dir, toolchain, profile):
        return False
    return True


def _read_text(path):
    with open(path) as f:
        return f.read()


def _build_uses_vcpkg(builder):
    """True if the build graph contains a vcpkg target (some built target
    referenced a `vcpkg#...` dependency). get_build_targets() is the build set
    with command-line exclusions already applied, so excluding the only vcpkg
    target makes this False -> the install is skipped."""
    for target in builder.get_build_targets().values():
        if getattr(target, 'type', None) == 'vcpkg_library':
            return True
    return False


def _auto_dynamic_ports(builder, packages):
    """The 'auto' ports that a dynamic_link binary actually depends on.

    Mirrors cc_library's generate_dynamic: a dynamic_link binary's
    _expand_deps_generation sets attr['generate_dynamic']=True on each
    VcpkgLibrary in its dependency closure during analyze (which runs before
    setup()), so the flag now tells us exactly which 'auto' ports need a shared
    library built. Returns a sorted, deduplicated port list."""
    auto = set(auto_ports(packages))
    if not auto:
        return []
    demanded = set()
    for target in builder.get_build_targets().values():
        if getattr(target, 'type', None) != 'vcpkg_library':
            continue
        if not target.attr.get('generate_dynamic'):
            continue
        port = getattr(target, '_vcpkg_port', None)
        if port in auto:
            demanded.add(port)
    return sorted(demanded)


def shared_install_root(base):
    """Install root for the shared (`-shared` triplet) tree.

    A SEPARATE root from the main install: vcpkg manifest mode "owns" its
    install root and prunes anything not in the current manifest, so sharing one
    root would make the second (subset) install wipe the first."""
    return os.path.join(base, 'shared', 'installed')


def _install_shared(vcpkg_bin, cfg, vanilla, ports, packages,
                    base, triplets_dir, toolchain, profile):
    """Install `ports` as shared libraries into the `blade-<triplet>-shared`
    tree (a separate manifest + overlay triplet + install root, since vcpkg
    builds one linkage per triplet). Returns True on success or a stamp-skip."""
    import hashlib
    import json
    from blade import console, util
    shared_overlay = shared_overlay_triplet_name(vanilla)
    chainload = not toolchain.cc_is('msvc')
    triplet_cmake = overlay_triplet_cmake(
        toolchain.target_os, toolchain.target_arch,
        library_linkage='dynamic',
        cmake_options=port_cmake_options({p: packages[p] for p in ports}),
        build_type=vcpkg_build_type(vanilla, profile),
        chainload=chainload)
    if triplet_cmake is None:  # pragma: no cover - main triplet already validated
        return True
    shared_base = os.path.join(base, 'shared')
    shared_installed = shared_install_root(base)
    os.makedirs(shared_base, exist_ok=True)
    subset = {p: packages[p] for p in ports}
    manifest = json.dumps(manifest_json(subset, cfg.get('baseline', '')),
                          indent=2, sort_keys=True)
    files = {
        os.path.join(shared_base, 'vcpkg.json'): manifest,
        os.path.join(triplets_dir, shared_overlay + '.cmake'): triplet_cmake,
    }
    configuration = configuration_json(cfg.get('registries') or [])
    if configuration is not None:
        files[os.path.join(shared_base, 'vcpkg-configuration.json')] = json.dumps(
            configuration, indent=2, sort_keys=True)
    for path, content in files.items():
        util.write_if_changed(path, content)

    stamp = hashlib.md5(
        (manifest + triplet_cmake + shared_overlay).encode()).hexdigest()
    stamp_file = os.path.join(shared_base, '.blade-vcpkg-stamp')
    if (os.path.isdir(os.path.join(shared_installed, shared_overlay))
            and os.path.exists(stamp_file)
            and _read_text(stamp_file).strip() == stamp):
        return True

    cmd = [vcpkg_bin, 'install',
           '--triplet', shared_overlay,
           '--x-manifest-root', shared_base,
           '--x-install-root', shared_installed,
           '--overlay-triplets', triplets_dir]
    binary_cache = cfg.get('binary_cache') or 'auto'
    if binary_cache != 'auto':
        cmd.append('--binarysource=' + binary_cache)
    console.info('vcpkg: installing %d shared package(s) for %s ...'
                 % (len(ports), shared_overlay))
    if not _run_install_with_progress(cmd):
        return False
    with open(stamp_file, 'w') as f:
        f.write(stamp)
    return True


def _run_install_with_progress(cmd):
    """Run `vcpkg install`, rendering its `Installing N/M ...` stream as blade's
    live build panel. Returns True on success; on failure prints the captured
    output and returns False. Off a TTY the panel is a no-op (CI logs show the
    output only on failure)."""
    import collections
    import subprocess
    import time
    from blade import console
    progress_re = re.compile(r'Installing (\d+)/(\d+)\s+(\S+)')
    recent = collections.deque(maxlen=4)
    captured = []
    total = 0
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            errors='replace', bufsize=1)
    start = time.time()
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip('\r\n')
        captured.append(line)
        m = progress_re.search(line)
        if m:
            current, total = int(m.group(1)), int(m.group(2))
            recent.append(m.group(3))
            elapsed = time.time() - start
            eta = (total - current) * elapsed / current if current else None
            # `current` is the package now installing -> current-1 finished.
            console.render_build_panel(current - 1, 1, total, list(recent), eta)
    proc.wait()
    if total:
        console.render_build_panel(total, 0, total, list(recent))
    console.clear_progress_bar()
    if proc.returncode != 0:
        console.error('vcpkg install failed:\n%s' % '\n'.join(captured))
        return False
    return True


_blade_target.register_dep_scheme('vcpkg', _vcpkg_dep_handler)
