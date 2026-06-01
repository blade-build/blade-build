# Copyright (c) 2026 Tencent Inc.
# All rights reserved.

"""System-library symbol enumeration for the cc check_undefined static check.

For each library blade needs to know the defined externals of (the toolchain's
default-linked set, plus every distinct ``#alias`` referenced as a dep across
the workspace), this module produces a sidecar ``.syms`` file containing one
symbol name per line.

The check rule consumes these files directly (no nm invocation in the per-
target check); regeneration happens only when the source library's
``(mtime, size)`` changes. That makes the check's hot path cheap and
deterministic, and avoids hand-maintaining a regex baseline.

Cache file format::

    # blade system-symbols cache v1
    # alias: <name>
    # source: <absolute path>
    # mtime: <unix seconds>
    # size: <bytes>
    <symbol>
    <symbol>
    ...

The four header lines are checked at consumption time; a mismatch in
``(mtime, size)`` against the live ``os.stat()`` triggers re-enumeration.
"""

import os
import subprocess

from blade import console
from blade.util import mkdir_p


_CACHE_FORMAT_VERSION = 5  # bumped: v5 keeps weak-defined V/W (typeinfo, vtables)
_CACHE_HEADER_LINES = 5  # version, alias, source, mtime, size


def _candidate_filenames(toolchain, alias):
    """File-name variants to try with ``cc -print-file-name=`` for an alias.

    Linux ``-l<x>`` resolution looks for ``lib<x>.so`` then ``lib<x>.a``; we
    try common ``.so.<N>`` variants too because that's what's actually
    installed (e.g. ``libc.so.6``). On macOS ``.dylib`` is the dynamic form;
    we also accept ``.tbd`` text-based dylib stubs because that's what Xcode
    ships for SDK libs.

    On Linux glibc, ``/usr/lib/.../libc.so`` is typically a GNU-ld linker
    script (``GROUP ( libc.so.6 libc_nonshared.a AS_NEEDED ... )``), not
    an ELF -- so we try the versioned forms FIRST, falling back to ``.so``
    only if no versioned variant is present. ``.so.6`` is libc/libm/libdl
    on glibc; ``.so.0`` for libdl on some distros; ``.so.1``/``.so.2`` for
    libgcc_s / various utility libs.
    """
    target = toolchain.target_os
    if target == 'darwin':
        return [
            f'lib{alias}.dylib',
            f'lib{alias}.tbd',
            f'lib{alias}.a',
        ]
    if target == 'windows':
        return [
            f'{alias}.lib',
            f'lib{alias}.a',
        ]
    # Linux / other ELF: versioned forms first to skip glibc linker scripts.
    return [
        f'lib{alias}.so.6',     # libc/libm/libdl on modern glibc
        f'lib{alias}.so.1',     # libgcc_s, libstdc++ (.so.6 is libstdc++)
        f'lib{alias}.so.2',
        f'lib{alias}.so.0',
        f'lib{alias}.so',       # last: usually a linker script on glibc
        f'lib{alias}.a',
    ]


_macos_sdk_path_cache = None


def _looks_like_binary_lib(path):
    """Sniff the file header. True for ELF / Mach-O / PE / .a / .tbd; False
    for GNU-ld linker scripts ('GROUP ( ... )', 'INPUT ( ... )', 'OUTPUT_FORMAT')
    that ``gcc -print-file-name`` happily returns instead of the real library."""
    try:
        with open(path, 'rb') as f:
            head = f.read(8)
    except OSError:
        return False
    if not head:
        return False
    # ELF, Mach-O (all 4 magics), PE / DOS stub ('MZ'), ar archive ('!<arch>')
    binary_prefixes = (
        b'\x7fELF',                 # ELF
        b'\xfe\xed\xfa\xce',         # Mach-O 32 BE
        b'\xfe\xed\xfa\xcf',         # Mach-O 64 BE
        b'\xce\xfa\xed\xfe',         # Mach-O 32 LE
        b'\xcf\xfa\xed\xfe',         # Mach-O 64 LE
        b'\xca\xfe\xba\xbe',         # universal Mach-O ('fat')
        b'MZ',                       # PE / .lib (COFF)
        b'!<arch>\n',                # Unix ar archive (.a)
    )
    if any(head.startswith(p) for p in binary_prefixes):
        return True
    # Apple .tbd is YAML text; our caller handles it via _tbd_extract_symbols.
    if path.endswith('.tbd'):
        return True
    return False


def _follow_linker_script(path):
    """Resolve a GNU-ld linker script to all of its real .so / .a inputs.

    Linker scripts that ``gcc -print-file-name`` returns for ``libc.so`` /
    ``libpthread.so`` look like::

        GROUP ( /lib/x86_64-linux-gnu/libc.so.6
                /usr/lib/x86_64-linux-gnu/libc_nonshared.a
                AS_NEEDED ( /lib64/ld-linux-x86-64.so.2 ) )

    Glibc splits its API across two members: the shared ``libc.so.6`` plus
    the static helper ``libc_nonshared.a`` (which holds ``__stack_chk_fail``,
    a few ``stat`` / ``__libc_csu_*`` wrappers, etc.). We enumerate ALL
    referenced .so / .a inputs and let the caller union their symbol sets.

    Returns a list of absolute paths (possibly empty). Skips ``AS_NEEDED``
    keyword and any non-absolute tokens.
    """
    try:
        with open(path, encoding='utf-8', errors='ignore') as f:
            text = f.read(8192)  # scripts are tiny; cap to avoid surprises
    except OSError:
        return []
    if not any(kw in text for kw in ('GROUP', 'INPUT', 'OUTPUT_FORMAT', 'AS_NEEDED')):
        return []
    # Strip /* ... */ comments and #-comments to keep tokenization simple.
    import re as _re
    text = _re.sub(r'/\*.*?\*/', ' ', text, flags=_re.S)
    text = _re.sub(r'#.*', ' ', text)
    results = []
    seen = set()
    for tok in _re.findall(r'[\w./+-]+', text):
        if tok in ('GROUP', 'INPUT', 'OUTPUT_FORMAT', 'AS_NEEDED', 'STARTUP'):
            continue
        if not (tok.endswith('.a') or '.so' in tok):
            continue
        if not os.path.isabs(tok) or not os.path.isfile(tok):
            continue
        real = os.path.realpath(tok)
        if real not in seen:
            seen.add(real)
            results.append(real)
    return results


def _macos_sdk_path():
    """Return the active macOS SDK root, or ``None`` if Xcode is unavailable.

    Cached at module level: ``xcrun --show-sdk-path`` is several hundred ms
    on first invocation, and the value is invariant for a build session.
    """
    global _macos_sdk_path_cache
    if _macos_sdk_path_cache is None:
        try:
            out = subprocess.check_output(['xcrun', '--show-sdk-path'],
                                           stderr=subprocess.DEVNULL,
                                           encoding='utf-8').strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            _macos_sdk_path_cache = ''
        else:
            _macos_sdk_path_cache = out if os.path.isdir(out) else ''
    return _macos_sdk_path_cache or None


def resolve_lib_path(toolchain, alias):
    """Locate the file on disk for system library ``alias``.

    Two-stage resolution:

    1. Ask the compiler driver via ``-print-file-name=``. Works for libgcc,
       libstdc++ on Linux, MinGW system libs, etc. The driver echoes the
       input back when it doesn't know the lib, which we filter via
       ``os.path.isfile``.
    2. On macOS, fall back to ``<sdk>/usr/lib/lib<alias>.tbd`` (and the
       ``.B.tbd`` versioned variant). System libs there don't exist on
       disk as ``.dylib`` files — they live in the dyld shared cache —
       so the Xcode SDK ships text-based stubs (``.tbd``) that we can
       enumerate symbols from. ``cc -print-file-name`` does not search
       the SDK.

    Returns ``None`` if no candidate resolves.
    """
    paths = resolve_lib_paths(toolchain, alias)
    return paths[0] if paths else None


def resolve_lib_paths(toolchain, alias):
    """Like ``resolve_lib_path`` but returns ALL backing files (a list).

    For most libraries the list is a single ``.so`` / ``.dylib`` / ``.tbd``.
    On Linux glibc the unversioned ``libc.so`` is a linker script bundling
    a shared lib and a static helper archive::

        GROUP ( /lib/.../libc.so.6 /usr/lib/.../libc_nonshared.a AS_NEEDED ( ld.so ) )

    Symbols like ``__stack_chk_fail`` live ONLY in the ``_nonshared.a``;
    we must enumerate every member to get a complete baseline.

    Empty list if the alias can't be resolved.
    """
    cc = toolchain.cc
    for candidate in _candidate_filenames(toolchain, alias):
        try:
            out = subprocess.check_output(
                [cc, f'-print-file-name={candidate}'],
                stderr=subprocess.DEVNULL,
                encoding='utf-8',
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        if not out or not os.path.isfile(out):
            continue
        # On Linux glibc, the unversioned .so is often a GNU-ld linker script
        # rather than a real ELF -- follow it to all real .so / .a members.
        if _looks_like_binary_lib(out):
            return [os.path.realpath(out)]
        members = _follow_linker_script(out)
        if members:
            return members
        # Neither binary nor a parseable linker script. Skip to next candidate.

    # macOS SDK fallback. Try lib<name>.tbd and lib<name>.B.tbd (versioned
    # form -- libSystem ships as libSystem.B.tbd alongside libSystem.tbd
    # which re-exports it; either works for symbol enumeration).
    if toolchain.target_os == 'darwin':
        sdk = _macos_sdk_path()
        if sdk:
            sdk_libdir = os.path.join(sdk, 'usr', 'lib')
            for candidate in (f'lib{alias}.tbd',
                              f'lib{alias}.B.tbd',
                              f'lib{alias}.dylib',
                              f'lib{alias}.a'):
                path = os.path.join(sdk_libdir, candidate)
                if os.path.isfile(path):
                    return [os.path.realpath(path)]
    return []


def _nm_defined_externals(lib_path):
    """Return the set of externally-defined symbol names in ``lib_path``.

    Portable across GNU binutils nm and Apple's nm:
      * GNU nm: ``-D`` (dynamic table), ``--defined-only``, ``--extern-only``
        all valid; we use them when available for the fast path on shared
        ELFs.
      * Apple nm: rejects GNU long options; uses plain ``-P -g`` (POSIX
        format, external-only) and we filter ``U``/``W`` out of the output.
        Apple nm also resolves ``.tbd`` text-based stubs by following the
        install_name into the dyld shared cache, so a ``.tbd`` input gives
        the real lib's symbol table at no extra cost.

    Universal binaries on macOS produce a per-architecture header
    (``<lib> (for architecture X):``) before each section's symbol list;
    we union symbols across all architectures since they're effectively
    the same export surface for our purposes (a missing dep on x86_64
    is a missing dep on arm64 too).

    Important: Apple's libSystem.B.tbd is a multi-document YAML stub --
    libSystem proper plus ~39 re-exported component libs (libsystem_c,
    libsystem_pthread, libsystem_m, ...) inlined into one file. Apple
    nm only enumerates the first document (which barely defines anything),
    so for ``.tbd`` inputs we go straight to the text parser, which
    sees the symbols of every embedded document.
    """
    if lib_path.endswith('.tbd'):
        # Skip nm: Apple's nm only enumerates the first YAML document.
        return _tbd_extract_symbols(lib_path)
    for argv in (
        # GNU/binutils fast path
        ['nm', '-D', '--defined-only', '--extern-only', '-P', lib_path],
        # Portable / Apple nm. -g = external-only (POSIX); we filter U/W.
        ['nm', '-P', '-g', lib_path],
    ):
        try:
            out = subprocess.check_output(argv, stderr=subprocess.DEVNULL,
                                          encoding='utf-8', errors='replace')
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        symbols = set()
        for raw in out.splitlines():
            line = raw.strip()
            if not line or line.endswith(':'):  # header / arch / member line
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            name, ty = parts[0], parts[1]
            # Skip undefined references only. Per nm(1):
            #   U  — undefined
            #   w  — weak undefined  (uppercase W is weak DEFINED, keep)
            #   v  — weak undefined object  (uppercase V is weak DEFINED, keep)
            # Everything else is some flavor of defined: T/t text, D/d data,
            # B/b bss, R/r rodata, A absolute, N debug, C common, S/s
            # section, V/W weak defined, i/I IFUNC, u unique global. With
            # nm -g / --extern-only already filtering to globals, both case
            # variants are link-time-resolvable and belong in the baseline.
            if ty in ('U', 'w', 'v'):
                continue
            # ELF symbol versioning: nm prints `foo@@GLIBCXX_3.4.21` for
            # the default version, `foo@GLIBCXX_3.4.21` for non-default.
            # The consumer's .o records the unversioned undefined `foo`;
            # strip the @VERSION suffix so both sides match.
            at = name.find('@')
            if at >= 0:
                name = name[:at]
            symbols.add(name)
        if symbols:
            return symbols
    # Last-ditch: parse .tbd YAML directly (used only if Apple nm can't
    # resolve the .tbd, which happens when the dyld shared cache for the
    # target architecture is unavailable).
    if lib_path.endswith('.tbd'):
        return _tbd_extract_symbols(lib_path)
    console.warning(
        'system_symbols: nm produced no symbols for %s (treating as empty)' % lib_path)
    return set()


def _tbd_extract_symbols(tbd_path):
    """Best-effort symbol extraction from an Apple ``.tbd`` text stub.

    .tbd files are YAML describing the symbols a system library exports.
    Apple libSystem ships as a single ``.tbd`` containing ~40 embedded YAML
    documents (libSystem itself plus all its re-exported component dylibs:
    libsystem_c, libsystem_pthread, libsystem_m, libdyld, libunwind, ...),
    so a flat text scan of the whole file naturally picks up everything
    that's actually reachable through ``-lSystem`` at link time.

    Rather than pull in a YAML parser for one consumer, we do a simple
    bracket-balanced text scan:

      1. Find each occurrence of one of the symbol-list keys
         (``symbols:``, ``weak-symbols:``, ``objc-classes:``,
         ``objc-ivars:``, ``objc-eh-types:``, ``re-exports:`` -- the last
         lists file paths which we deliberately skip).
      2. Read from the next ``[`` to its matching ``]`` (these blocks
         don't contain nested brackets).
      3. Split on commas / whitespace, strip quotes, drop empties.

    Objective-C class names appear in the YAML as bare identifiers (e.g.
    ``NSObject``); the corresponding linker symbol is ``_OBJC_CLASS_$_<n>``
    plus ``_OBJC_METACLASS_$_<n>`` -- we emit both forms so the check
    matches whatever's actually undefined in the user's archive.
    """
    symbols = set()
    try:
        with open(tbd_path, encoding='utf-8') as f:
            text = f.read()
    except OSError:
        return symbols

    # Symbol-list keys we care about, with a flag for "this list is class
    # names and needs the OBJC_CLASS_$_ prefix expansion".
    keys = [
        ('symbols', False),
        ('weak-symbols', False),
        ('objc-classes', True),
        ('objc-ivars', False),
        ('objc-eh-types', True),
    ]
    for key, is_objc_class in keys:
        marker = key + ':'
        idx = 0
        while True:
            pos = text.find(marker, idx)
            if pos < 0:
                break
            open_br = text.find('[', pos + len(marker))
            if open_br < 0:
                break
            close_br = text.find(']', open_br + 1)
            if close_br < 0:
                break
            idx = close_br + 1
            body = text[open_br + 1:close_br]
            # Split on commas; entries may span multiple lines so newlines
            # are just whitespace.
            for raw_name in body.split(','):
                name = raw_name.strip().strip('"\'')
                if not name:
                    continue
                if is_objc_class:
                    # The actual link-visible symbols for Objective-C
                    # classes are _OBJC_CLASS_$_<n> and _OBJC_METACLASS_$_<n>.
                    symbols.add('_OBJC_CLASS_$_' + name)
                    symbols.add('_OBJC_METACLASS_$_' + name)
                else:
                    symbols.add(name)
    return symbols


def _read_cache_header(cache_file):
    """Read the cache file's header. Returns ``(alias, source, mtime, size)``
    on success, ``None`` if the file is missing, truncated, or malformed."""
    try:
        with open(cache_file, encoding='utf-8') as f:
            head = [next(f, '') for _ in range(_CACHE_HEADER_LINES)]
    except OSError:
        return None
    if len(head) < _CACHE_HEADER_LINES:
        return None
    if not head[0].startswith('# blade system-symbols cache v'):
        return None
    try:
        version = int(head[0].rstrip().rsplit('v', 1)[-1])
    except ValueError:
        return None
    if version != _CACHE_FORMAT_VERSION:
        return None
    fields = {}
    for line in head[1:]:
        if not line.startswith('# '):
            return None
        try:
            key, val = line[2:].rstrip().split(': ', 1)
        except ValueError:
            return None
        fields[key] = val
    try:
        return (fields['alias'], fields['source'],
                int(fields['mtime']), int(fields['size']))
    except (KeyError, ValueError):
        return None


def _is_cache_valid(cache_file, alias, source_path):
    """Cache is valid when both (mtime, size) of ``source_path`` match the
    header, and the recorded alias still matches what we're asked for."""
    parsed = _read_cache_header(cache_file)
    if parsed is None:
        return False
    cached_alias, cached_source, cached_mtime, cached_size = parsed
    if cached_alias != alias or cached_source != source_path:
        return False
    try:
        st = os.stat(source_path)
    except OSError:
        return False
    return int(st.st_mtime) == cached_mtime and st.st_size == cached_size


def _write_cache(cache_file, alias, source_path, symbols):
    mkdir_p(os.path.dirname(cache_file))
    try:
        st = os.stat(source_path)
    except OSError as e:
        console.warning('system_symbols: could not stat %s: %s' % (source_path, e))
        return
    tmp = cache_file + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write('# blade system-symbols cache v%d\n' % _CACHE_FORMAT_VERSION)
        f.write('# alias: %s\n' % alias)
        f.write('# source: %s\n' % source_path)
        f.write('# mtime: %d\n' % int(st.st_mtime))
        f.write('# size: %d\n' % st.st_size)
        for s in sorted(symbols):
            f.write(s)
            f.write('\n')
    os.replace(tmp, cache_file)


def ensure_cache(toolchain, alias, cache_dir):
    """Ensure a ``.syms`` cache file exists for ``alias`` and is current.

    Returns the cache file path, or ``None`` if the library cannot be
    located (caller should treat as missing-from-baseline -- the per-target
    check will then surface real misses pointing at that lib's symbols).

    When the alias resolves to multiple files (e.g. glibc's linker script
    bundles libc.so.6 + libc_nonshared.a), union symbols from all of them;
    cache validity is keyed on the first file's (mtime, size) which is
    sufficient because the bundled members upgrade together.
    """
    sources = resolve_lib_paths(toolchain, alias)
    if not sources:
        return None
    primary = sources[0]
    cache_file = os.path.join(cache_dir, '%s.syms' % alias)
    if _is_cache_valid(cache_file, alias, primary):
        return cache_file
    symbols = set()
    for src in sources:
        symbols |= _nm_defined_externals(src)
    _write_cache(cache_file, alias, primary, symbols)
    return cache_file


def read_symbols(cache_file):
    """Read symbol names from a cache file produced by ``ensure_cache``.

    Header lines (starting with ``#``) are skipped; everything else is a
    symbol name. Returns an empty set if the file is missing or malformed.
    """
    if not cache_file:
        return set()
    try:
        with open(cache_file, encoding='utf-8') as f:
            return {line.rstrip() for line in f
                    if line.strip() and not line.startswith('#')}
    except OSError:
        return set()
