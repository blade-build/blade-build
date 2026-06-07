# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: Feng Chen <phongchen@tencent.com>


"""
Manage symbols can be used in BUILD files.
"""


class Native:
    """
    A built-in object to support native rules and other helper functions.
    make native rules such as `cc_library` can always be accessed in the form of `native.cc_library`.
    """


__build_rules = {}

# Names visible ONLY inside extension (`.bld`) files, never in BUILD files --
# e.g. `define_rule` / `attr` for custom rules (#829). Mirrors how Bazel exposes
# `rule`/`attr` as top-level builtins only in `.bzl`.
__extension_only = {}

__native = Native()

def register_variable(name, value):
    """Register a variable that accessiable in BUILD file."""
    __build_rules[name] = value
    setattr(__native, name, value)


def register_function(f):
    """Register a function as a build rule that callable in BUILD file."""
    register_variable(f.__name__, f)


def register_extension_variable(name, value):
    """Register a name visible only in extension (`.bld`) files, not BUILD."""
    __extension_only[name] = value


def get_all():
    """Get the globals dict"""
    result = __build_rules.copy()
    return result


def get_all_for_extension():
    """Get the globals dict; 'native' and extension-only names (define_rule,
    attr) are visible to extensions but not to BUILD files."""
    result = get_all()
    result['native'] = __native
    result.update(__extension_only)
    return result
