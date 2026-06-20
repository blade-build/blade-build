# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Sanitizer selection: parse --sanitizer into -fsanitize flags + a build tag.

A sanitizer is a per-run choice (a command-line flag), not project config.
This first phase supports AddressSanitizer; ThreadSanitizer / UBSan / etc. are
added in later phases (see blade-build#1038). The parsed set is canonical
(deduplicated and sorted) so it drives both the -fsanitize= flag list and the
build-dir tag identically regardless of argument order.
"""


from blade import console

# Accepted --sanitizer name (and short alias) -> canonical -fsanitize= name.
_ALIASES = {
    'address': 'address',
    'asan': 'address',
    'undefined': 'undefined',
    'ubsan': 'undefined',
    'leak': 'leak',
    'lsan': 'leak',
    'thread': 'thread',
    'tsan': 'thread',
}

# Canonical -fsanitize= name -> short build-dir tag.
_TAGS = {
    'address': 'asan',
    'undefined': 'ubsan',
    'leak': 'lsan',
    'thread': 'tsan',
}

# Canonical name -> the sanitizers it cannot be combined with. Each uses a
# different shadow-memory / runtime model, so they're mutually exclusive;
# `undefined` is pure instrumentation and composes with anything. (`memory`
# is listed ahead of its phase so the matrix stays complete.)
_INCOMPATIBLE = {
    'address': {'thread', 'memory'},
    'leak': {'thread', 'memory'},
    'thread': {'address', 'leak', 'memory'},
    'memory': {'address', 'leak', 'thread'},
}


def parse(value):
    """Parse a --sanitizer value into a sorted list of canonical names.

    Empty / None -> ``[]`` (off). An unknown name is a fatal error.
    """
    if not value:
        return []
    canonical = set()
    for name in value.split(','):
        name = name.strip().lower()
        if not name:
            continue
        if name not in _ALIASES:
            console.fatal('Unknown --sanitizer "%s" (supported: %s)' %
                          (name, ', '.join(sorted(_ALIASES))))
        canonical.add(_ALIASES[name])
    return sorted(canonical)


def fsanitize_value(sanitizers):
    """The value for ``-fsanitize=`` (e.g. ``address``)."""
    return ','.join(sanitizers)


def compile_flags(sanitizers):
    """Compile flags for the active sanitizer set."""
    # Frame pointers + debug info for readable, symbolized reports.
    flags = ['-fsanitize=' + fsanitize_value(sanitizers),
             '-fno-omit-frame-pointer', '-g']
    if 'undefined' in sanitizers:
        # Make UBSan findings fatal so a test actually fails on them, instead
        # of just printing a diagnostic and continuing (the default).
        flags.append('-fno-sanitize-recover=undefined')
    return flags


def link_flags(sanitizers):
    """Link flags for the active sanitizer set (pull in the runtime)."""
    return ['-fsanitize=' + fsanitize_value(sanitizers)]


def build_tag(sanitizers):
    """The build-dir tag for the set (e.g. ``asan``); stable, sorted."""
    return '+'.join(_TAGS[s] for s in sanitizers)


def runtime_env(sanitizers):
    """Default ``*_OPTIONS`` env so a detection reliably fails the test.

    These are defaults only -- the test runner applies them without overriding
    a value the user already set in the environment.
    """
    env = {}
    if 'address' in sanitizers:
        env['ASAN_OPTIONS'] = 'abort_on_error=1'
    if 'thread' in sanitizers:
        env['TSAN_OPTIONS'] = 'halt_on_error=1'
    if 'undefined' in sanitizers:
        env['UBSAN_OPTIONS'] = 'halt_on_error=1:print_stacktrace=1'
    if 'leak' in sanitizers:
        env['LSAN_OPTIONS'] = 'exitcode=1'
    return env


def check_compat(sanitizers):
    """Fatal if the requested sanitizers can't be combined with each other."""
    requested = set(sanitizers)
    for s in sanitizers:
        conflicts = _INCOMPATIBLE.get(s, set()) & requested
        if conflicts:
            console.fatal('--sanitizer: "%s" cannot be combined with %s' %
                          (s, ', '.join(sorted(conflicts))))


def check_toolchain(sanitizers, toolchain):
    """Fatal if the active toolchain can't provide a requested sanitizer."""
    if not sanitizers:
        return
    if toolchain.cc_is('msvc'):
        # MSVC /fsanitize=address support is a later phase (#1038 Phase 3).
        console.fatal('--sanitizer is not supported on the MSVC toolchain yet')
