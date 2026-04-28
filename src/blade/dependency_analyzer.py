# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Huan Yu <huanyu@tencent.com>
#         Feng Chen <phongchen@tencent.com>
#         Yi Wang <yiwang@tencent.com>
#         Chong Peng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
This is the dependencies expander module which accepts the targets loaded
from BUILD files and will find all of the targets needed by the target and
add extra options according to different target types.
"""


from blade import console



def analyze_deps(related_targets):
    """
    Analyze the dependency relationship between targets.

    Given the map of related targets, i.e., the subset of target_database
    that are dependencies of those targets speicifed in Blade command
    line, this utility class expands the 'deps' property of each target
    to be all direct and indirect dependencies of that target.

    After expanded the dependencies of targets, sort the topologically
    and then provide the query interface to users by blade manager.

    Input: related targets after loading targets from BUILD files.
           {target_key : (target_data), ...}

    Output:
        1. the targets that are expanded
            {target_key : (target_data with deps expanded), ...}
        2. the keys sorted
            [all the targets keys] - sorted
    """
    _expand_deps(related_targets)
    _expand_dependents(related_targets)
    for target in related_targets.values():
        target.check_visibility()
    # The topological sort is very important because even if ninja doesn't require the order of build statements,
    # but when generating code, dependents may access dependency's generated file information, which requires generation
    # of dependency ran firstly.
    return _topological_sort(related_targets)


def _expand_deps(targets):
    """_expand_deps.

    Find out all the targets that certain target depeneds on them.
    Fill the related options according to different targets.

    """
    for target_id in targets:
        target = targets[target_id]
        _expand_target_deps(target_id, targets)
        target._expand_deps_generation()


def _unique_deps(new_deps_list):
    """Unique dependency list, for duplicate items only keep the later ones."""
    result = []
    deps = set()
    for dep in reversed(new_deps_list):
        if dep not in deps:
            result.append(dep)
            deps.add(dep)
    return list(reversed(result))


def _expand_target_deps(target_id, targets, root_targets=None):
    """_expand_target_deps.

    Return all targets depended by target_id directly and/or indirectly.
    We need the parameter root_target_id to check loopy dependency.

    """
    target = targets[target_id]
    if target.expanded_deps is not None:
        return target.expanded_deps

    if root_targets is None:
        root_targets = set()

    root_targets.add(target_id)
    new_deps_list = []

    for d in target.deps:
        # loop dependency
        if d in root_targets:
            err_msg = ''
            for t in root_targets:
                err_msg += '//%s --> ' % t
            console.fatal('Loop dependency found: //{} --> [{}]'.format(d, err_msg))
        new_deps_list.append(d)
        new_deps_list += _expand_target_deps(d, targets, root_targets)

    new_deps_list = _unique_deps(new_deps_list)
    target.expanded_deps = new_deps_list
    root_targets.remove(target_id)

    return new_deps_list


def _expand_dependents(related_targets):
    """Build and expand dependents for every targets.
    Args:
        related_targets: dict{target_key, target} to be built
    """
    for target_key, target in related_targets.items():
        for depkey in target.deps:
            related_targets[depkey].dependents.add(target_key)
        for depkey in target.expanded_deps:
            related_targets[depkey].expanded_dependents.add(target_key)


def _topological_sort(related_targets):
    """Sort the target keys according to their dependency relationship.
    Every dependents before their dependencies, because the dependents should be built earlier.
    Args:
        related_targets: dict{target_key, target} to be built
    Returns:
        sorted_target_key, sorted target keys.
    """
    numpreds = {}  # elt -> # of predecessors
    q = []
    for target_key, target in related_targets.items():
        dep_len = len(target.deps)
        numpreds[target_key] = dep_len
        if dep_len == 0:
            q.append(target_key)
    # for everything in queue, knock down the pred count on its dependents
    sorted_target_keys = []
    while q:
        key = q.pop()
        sorted_target_keys.append(key)
        for depkey in related_targets[key].dependents:
            numpreds[depkey] -= 1
            if numpreds[depkey] == 0:
                q.append(depkey)
    assert len(sorted_target_keys) == len(related_targets)
    return sorted_target_keys
