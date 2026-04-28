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

__native = Native()

def register_variable(name, value):
    """Register a variable that accessiable in BUILD file."""
    __build_rules[name] = value
    setattr(__native, name, value)


def register_function(f):
    """Register a function as a build rule that callable in BUILD file."""
    register_variable(f.__name__, f)


def get_all():
    """Get the globals dict"""
    result = __build_rules.copy()
    return result


def get_all_for_extension():
    """Get the globals dict, 'native' is only visible to extensions."""
    result = get_all()
    result['native'] = __native
    return result
