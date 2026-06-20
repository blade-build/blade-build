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
}

# Canonical -fsanitize= name -> short build-dir tag.
_TAGS = {
    'address': 'asan',
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


def build_tag(sanitizers):
    """The build-dir tag for the set (e.g. ``asan``); stable, sorted."""
    return '+'.join(_TAGS[s] for s in sanitizers)


def check_toolchain(sanitizers, toolchain):
    """Fatal if the active toolchain can't provide a requested sanitizer."""
    if not sanitizers:
        return
    if toolchain.cc_is('msvc'):
        # MSVC /fsanitize=address support is a later phase (#1038 Phase 3).
        console.fatal('--sanitizer is not supported on the MSVC toolchain yet')
