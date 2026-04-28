# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>
# Date:   Jan 27, 2021


"""
The target pattern module.
"""


import os

from blade import console
from blade import util


def _split(target):
    """Split target patten into path and name."""
    if ':' in target:
        path, name = target.rsplit(':', 1)
    else:
        if target.endswith('...'):
            path = target[:-3]
            name = '...'
        else:
            path = target
            name = '*'
    path = os.path.normpath(path)
    if path == '.':
        path = ''
    return path, name


def normalize(target, working_dir):
    """Normalize target from command line form into canonical form.

    Target canonical form: dir:name
        dir: relative to blade_root_dir, use '.' for blade_root_dir
        name: name  if target is dir:name
              '*'   if target is dir
              '...' if target is dir/...
    """
    if target.startswith('//'):
        target = target[2:]
    elif target.startswith('/'):
        console.error('Invalid target "%s" starting from root path.' % target)
        target = target[1:]  # Try correct to keep going
    else:  # Relative path
        if working_dir != '.':
            target = os.path.join(working_dir, target)
    path, name = _split(target)
    return '{}:{}'.format(path, name)


def normalize_list(targets, working_dir):
    """Normalize target list from command line form into canonical form."""
    return [normalize(target, working_dir) for target in targets]


def normalize_str_list(targets, working_dir, sep):
    """Parse and normalize a target pattern list string. Any empty part is removed."""
    return normalize_list(filter(bool, map(str.strip, targets.split(sep))), working_dir)


def match(target_id, pattern):
    """Check whether a atrget id match a target pattern"""
    t_path, t_name = target_id.split(':')
    p_path, p_name = pattern.split(':')

    if p_name == '...':
        return util.path_under_dir(t_path, p_path)
    if p_name == '*':
        return t_path == p_path
    return target_id == pattern


def is_valid_in_build(pattern):
    """Is a valid target pattern in BUILD file"""
    return pattern.startswith('//') or pattern.startswith(':')
