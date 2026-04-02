# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Huan Yu <huanyu@tencent.com>
#         Feng Chen <phongchen@tencent.com>
#         Yi Wang <yiwang@tencent.com>
#         Chong Peng <michaelpeng@tencent.com>
#         Wenting Li <wentingli@tencent.com>
# Date:   October 20, 2011


"""
This is the CmdOptions module which parses the users'
input and provides hint for users.
"""

from __future__ import absolute_import
from __future__ import print_function

import os
import traceback
import types

from blade import build_attributes
from blade import build_rules
from blade import config
from blade import console
from blade import dsl_api
from blade import restricted
from blade import target_tags

from blade.pathlib import Path
from blade.util import path_under_dir, var_to_list, exec_file, source_location


# import these modules make build functions registered into build_rules
# TODO(chen3feng): Load build modules dynamically to enable extension.


def _load_build_rules():
    # pylint: disable=import-outside-toplevel,unused-import
    import blade.cc_targets
    import blade.cu_targets
    import blade.gen_rule_target
    import blade.go_targets
    import blade.java_targets
    import blade.scala_targets
    import blade.lex_yacc_target
    import blade.package_target
    import blade.proto_library_target
    import blade.py_targets
    import blade.resource_library_target
    import blade.sh_test_target
    import blade.swig_library_target
    import blade.thrift_library
    import blade.fbthrift_library

    build_rules.register_variable('build_target', build_attributes.attributes)


def _find_dependent(dkey, blade):
    """Find which target depends on the target with dkey."""
    target_database = blade.get_target_database()
    for key in target_database:
        target = target_database[key]
        if dkey in target.deps:
            return target
    return None


def _find_dir_dependent(dir, blade):
    """Find which target depends on the dir."""
    target_database = blade.get_target_database()
    for key in target_database:
        target = target_database[key]
        for dkey in target.deps:
            if dkey.split(':')[0] == dir:
                return target
    return None


def _report_not_exist(kind, path, source_dir, blade):
    """Report dir or BUILD file does not exist."""
    msg = '%s "//%s" does not exist' % (kind, path)
    dependent = _find_dir_dependent(source_dir, blade)
    (dependent or console).error(msg)


def enable_if(cond, true_value, false_value=None):
    """A global function can be called in BUILD to filter srcs/deps by target"""
    if cond:
        ret = true_value
    else:
        ret = false_value
    if ret is None:
        ret = []
    return ret


def _current_source_location():
    """Return source location in current BUILD file"""
    from blade import build_manager  # pylint: disable=import-outside-toplevel
    source_dir = Path(build_manager.instance.get_current_source_path())
    return source_location(os.path.join(str(source_dir), 'BUILD'))


def glob(include, exclude=None, excludes=None, allow_empty=False):
    """This function can be called in BUILD to specify a set of files using patterns.
    Args:
        include:List[str], file patterns to be matched.
        exclude:Optional[List[str]], file patterns to be removed from the result.
        allow_empty:bool: Whether a empty result is a error.

    Patterns may contain shell-like wildcards, such as * , ? , or [charset].
    Additionally, the path element '**' matches any subpath.
    """
    from blade import build_manager  # pylint: disable=import-outside-toplevel
    source_dir = Path(build_manager.instance.get_current_source_path())
    source_loc = _current_source_location()
    include = var_to_list(include)
    severity = config.get_item('global_config', 'glob_error_severity')
    if excludes:
        console.diagnose(source_loc, severity, '"excludes" is deprecated, use "exclude" instead')
    exclude = var_to_list(exclude) + var_to_list(excludes)

    def includes_iterator():
        results = []
        for pattern in include:
            if not pattern:
                console.diagnose(source_loc, 'error', '"glob": Empty pattern is not allowed')
                continue
            for path in source_dir.glob(pattern):
                if path.is_file() and not path.name.startswith('.'):
                    results.append(path.relative_to(source_dir))

        return results

    def is_special(pattern):
        return '*' in pattern or '?' in pattern or '[' in pattern

    non_special_excludes = set()
    match_excludes = set()
    for pattern in exclude:
        if is_special(pattern):
            match_excludes.add(pattern)
        else:
            non_special_excludes.add(pattern)

    def exclusion(path):
        if str(path) in non_special_excludes:
            return True
        for pattern in match_excludes:
            ret = path.match(pattern)
            if ret:
                return True
        return False

    result = sorted({str(p) for p in includes_iterator() if not exclusion(p)})
    if not result and not allow_empty:
        args = repr(include)
        if exclude:
            args += ', exclude=%s' % repr(exclude)
        console.diagnose(source_loc, severity,
                         '"glob(%s)" got an empty result. If it is the expected behavior, '
                         'specify "allow_empty=True" to eliminate this message' % args)

    return result


def _get_globals_for_build_file(source_dir):
    """Get global variables for BUILD files."""
    result = build_rules.get_all()
    global_config = config.get_section('global_config')
    if global_config.get('restricted_dsl') and source_dir not in global_config.get('unrestricted_dsl_dirs'):
        result['__builtins__'] = restricted.safe_builtins
    result['blade'] = dsl_api.get_blade_module()
    return result



def _get_globals_for_extension():
    """Get global variables for loadable extensions."""
    result = build_rules.get_all_for_extension()
    global_config = config.get_section('global_config')
    if global_config.get('restricted_dsl'):
        result['__builtins__'] = restricted.safe_builtins
    result['blade'] = dsl_api.get_blade_module()
    return result


# Each include in a BUILD file can only affect itself
__current_globals = None


def _expand_include_path(name):
    """Expand and normalize path to be loaded"""
    from blade import build_manager  # pylint: disable=import-outside-toplevel
    if name.startswith('//'):
        return name[2:]
    dir = build_manager.instance.get_current_source_path()
    return os.path.join(dir, name)


def include(name):
    """Include another file into current BUILD file"""
    full_path = _expand_include_path(name)
    if not os.path.isfile(full_path):
        console.diagnose(_current_source_location(), 'error', 'File "%s" does not exist' % name)
        return
    exec_file(full_path, __current_globals, None)


# Loaded extensions information
# dict{full_path: dict{symbol_name: value}}
__loaded_extension_info = {}


def _load_extension(name):
    """Load symbols from file or obtain from loaded cache."""
    full_path = _expand_include_path(name)
    if full_path in __loaded_extension_info:
        return __loaded_extension_info[full_path]

    if not os.path.isfile(full_path):
        console.diagnose(_current_source_location(), 'error', 'File "%s" does not exist' % name)
        return {}

    # The symbols in the current context should be invisible to the extension,
    # make an isolated symbol set to implement this approach.
    origin_globals = _get_globals_for_extension()
    extension_globals = origin_globals.copy()
    exec_file(full_path, extension_globals, None)
    # Extract new symbols
    result = {}
    for symbol, value in extension_globals.items():
        if symbol.startswith('_'):
            continue
        if symbol in origin_globals and value is origin_globals[symbol]:
            continue
        if isinstance(value, types.ModuleType):
            continue
        result[symbol] = value
    __loaded_extension_info[full_path] = result
    return result


def load(name, *symbols, **aliases):
    """Load and import symbols into current calling BUILD file
    Args:
        name: str, file name to be loaded.
        symbols: str*, symbol names to be imported.
        aliases: alias_name='real_name'*, symbol name to be imported as alias.
    """
    src_loc = _current_source_location()
    if not symbols and not aliases:
        console.diagnose(src_loc, 'error', 'The symbols to be imported must be explicitly declared')

    extension_globals = _load_extension(name)

    def error(symbol):
        console.diagnose(src_loc, 'error', '"%s" is not defined in "%s"' % (symbol, name))

    if '*' in symbols:
        # Wildcard import import all symbols except aliases.
        if len(symbols) != 1:
            console.diagnose(src_loc, 'error', "wildcard import can't coexist with named imports")
            return
        for symbol in extension_globals:
            if symbol not in aliases:
                __current_globals[symbol] = extension_globals[symbol]
    else:
        # Only import declared symbols into current file
        for symbol in symbols:
            if symbol not in extension_globals:
                error(symbol)
                continue
            __current_globals[symbol] = extension_globals[symbol]

    for alias, real_name in aliases.items():
        if real_name not in extension_globals:
            error(real_name)
            continue
        __current_globals[alias] = extension_globals[real_name]


build_rules.register_function(enable_if)
build_rules.register_function(glob)
build_rules.register_function(include)
build_rules.register_function(load)


def __load_build_file(source_dir, blade):
    """
    Load and execute the BUILD file, which is a Python script, in source_dir.
    Statements in BUILD depends on global variable current_source_dir, and will
    register build target/rules into global variables target_database.
    Report error and exit if path/BUILD does NOT exist.
    """

    if not os.path.isdir(source_dir):
        _report_not_exist('Directory', source_dir, source_dir, blade)
        return False

    old_current_source_path = blade.get_current_source_path()
    try:
        blade.set_current_source_path(source_dir)
        build_file = os.path.join(source_dir, 'BUILD')
        if os.path.isfile(build_file):
            try:
                # The magic here is that a BUILD file is a Python script,
                # which can be loaded and executed by execfile().
                global __current_globals
                __current_globals = _get_globals_for_build_file(source_dir)
                exec_file(build_file, __current_globals, None)
                return True
            except SystemExit:
                console.fatal('%s: Fatal error' % build_file)
            except:  # pylint: disable=bare-except
                console.fatal('Parse error in %s\n%s' % (
                    build_file, traceback.format_exc()))
        else:
            _report_not_exist('File', build_file, source_dir, blade)
    finally:
        blade.set_current_source_path(old_current_source_path)

    return False


def _load_build_file(source_dir, processed_dirs, blade):
    """
    Load the BUILD and place the targets into database.
    The parameters processed_dirs refers to a dict defined in the
    caller and used to avoid duplicated execution of BUILD files.
    """
    source_dir = os.path.normpath(source_dir)
    if source_dir in processed_dirs:
        return processed_dirs[source_dir]
    result = __load_build_file(source_dir, blade)
    processed_dirs[source_dir] = result
    return result


_BLADE_SKIP_FILE = '.bladeskip'

# File names should be skipped
_SKIP_FILES = ['BLADE_ROOT', _BLADE_SKIP_FILE]

# TODO: Eliminate hardcoded
_BUILD_DIRS = {'build32_debug', 'build32_release', 'build64_debug', 'build64_release'}


def _check_under_skipped_dir(dirname):
    """
    Check whether the directory is under a directory which contains a `.bladeskip` file or
    a nested workspace.

    Return:
        Full path of the skip file or empty if it is not under a skipped dir.
    """
    cache = _check_under_skipped_dir.cache
    if dirname in cache:
        return cache[dirname]
    if dirname in ('.', ''):
        return ''
    for skipfile in _SKIP_FILES:
        filepath = os.path.join(dirname, skipfile)
        if os.path.exists(filepath):
            cache[dirname] = filepath
            return filepath
    parent = os.path.dirname(dirname)
    if parent == dirname:
        return ''
    result = _check_under_skipped_dir(parent)
    cache[dirname] = result
    return result


_check_under_skipped_dir.cache = {}


def _has_load_excluded_file(root, files):
    """Whether exclude this root directory when loading BUILD."""
    if root == '.':
        return False
    # 'BLADE_ROOT' file under a subdirectory means it is a nested other workspace.
    if 'BLADE_ROOT' in files:
        console.info('Skip nested workspace "%s"' % root)
        return True
    if _BLADE_SKIP_FILE in files:
        console.info('Skip "%s" due to the "%s" file' % (root, _BLADE_SKIP_FILE))
        return True
    return False


def _is_load_excluded_dir(root, dir):
    """Whether exclude the directory when loading BUILD."""
    # Exclude directories starting with '.', e.g. '.svn', '.git', '.vscode'.
    if dir.startswith('.'):
        return True

    # Exclude build dirs
    if root == '.' and dir in _BUILD_DIRS:
        return True

    return False


def load_targets(target_ids, excluded_targets, blade):
    """load_targets.

    Parse and load targets, including those specified in command line
    and their direct and indirect dependencies, by loading related BUILD
    files.  Returns a map which contains all these targets.
    """
    _load_build_rules()

    filter_function = _compile_filter(blade)

    excluded_targets, excluded_dirs, excluded_trees = _parse_excluded_targets(excluded_targets)
    # targets specified in command line
    # starting dirs mentioned in command line
    direct_targets, starting_dirs = _expand_target_patterns(blade, target_ids, excluded_trees)
    starting_dirs -= excluded_dirs
    # to prevent duplicated loading of BUILD files
    processed_dirs = {}

    command_targets = _load_starting_build_files(blade, starting_dirs, processed_dirs, filter_function)
    command_targets |= direct_targets
    command_targets -= excluded_targets

    # load all their dependencies
    related_targets = _load_related_build_files(blade, command_targets, processed_dirs)

    return direct_targets, command_targets, related_targets


def _compile_filter(blade):
    expr = blade.get_options().tags_filter
    if not expr:
        return None

    filter_function, error = target_tags.compile_filter(expr)
    if error:
        console.error('Invalid "--tags-filter" expression: ' + error)
    return filter_function


def _parse_excluded_targets(excluded_targets):
    """Parse the excluded target patterns into different kinds."""
    # path:name, path:* and path:...
    direct_targets, excluded_dirs, excluded_trees = set(), set(), set()
    for target in excluded_targets:
        path, name = target.split(':')
        if not os.path.isdir(path):
            console.warning('--exclude-targets: directory "%s" doesn\'t exist' % path)
            continue
        if name == '*':
            excluded_dirs.add(path)
            continue
        if name == '...':
            excluded_trees.add(path)
            continue
        direct_targets.add(target)
    return direct_targets, excluded_dirs, excluded_trees


def _expand_target_patterns(blade, target_ids, excluded_trees):
    """Expand target patterns from command line."""
    # Parse command line target_ids. For those in the form of <path>:<target>,
    # record (<path>,<target>) in direct_targets; for the rest (with <path>
    # but without <target>), record <path> into starting_dirs.

    def under_excluded_trees(source_dir):
        if source_dir.startswith('./'):
            source_dir = source_dir[2:]
        if source_dir in excluded_trees:
            return True
        for dir in excluded_trees:
            if path_under_dir(source_dir, dir):
                return True
        return False

    direct_targets = set()
    starting_dirs = set()

    for target_id in target_ids:
        source_dir, target_name = target_id.rsplit(':', 1)

        if source_dir == '':
            source_dir = '.'
        elif not os.path.exists(source_dir):
            _report_not_exist('Directory', source_dir, source_dir, blade)

        skip_file = _check_under_skipped_dir(source_dir)
        if skip_file:
            console.warning('"%s" is under skipped directory due to "%s", ignored' % (target_id, skip_file))
            continue

        if target_name == '...':
            for root, dirs, files in os.walk(source_dir):
                # Note the dirs[:] = slice assignment; we are replacing the
                # elements in dirs (and not the list referred to by dirs) so
                # that os.walk() will not process deleted directories.
                if under_excluded_trees(root) or _has_load_excluded_file(root, files):
                    dirs[:] = []
                    continue
                dirs[:] = [d for d in dirs if not _is_load_excluded_dir(root, d)]
                if 'BUILD' in files:
                    starting_dirs.add(root)
        elif target_name == '*':
            starting_dirs.add(source_dir)
        else:
            direct_targets.add(target_id)

    return direct_targets, starting_dirs


def _load_starting_build_files(blade, starting_dirs, processed_dirs, filter_function):
    """Load all build files in starting_dirs."""

    # Load BUILD files in paths, and return all loaded targets.
    # Together with above step, we can ensure that all targets mentioned in the
    # command line are now loaded.

    for source_dir in starting_dirs:
        _load_build_file(source_dir, processed_dirs, blade)
    target_database = blade.get_target_database()
    if not filter_function:
        return set(target_database.keys())
    return {key for key, target in target_database.items() if filter_function(target)}


def _load_related_build_files(blade, command_targets, processed_dirs):
    """Load all related build files referenced by command line targets."""

    # Starting from targets specified in command line, breath-first
    # propagate to load BUILD files containing directly and indirectly
    # dependent targets.  All these targets form related_targets,
    # which is a subset of target_database created by loading  BUILD files.

    target_database = blade.get_target_database()
    related_targets = {}
    cited_targets = set(command_targets)

    while cited_targets:
        target_id = cited_targets.pop()
        source_dir, target_name = target_id.split(':')

        if target_id in related_targets:
            continue

        if source_dir == '#':
            related_targets[target_id] = target_database[target_id]
            continue

        skip_file = _check_under_skipped_dir(source_dir)
        if skip_file:
            dependent = _find_dependent(target_id, blade)
            dependent.error('"%s" is under skipped directory due to "%s"' % (target_id, skip_file))
            continue

        if not _load_build_file(source_dir, processed_dirs, blade):
            continue

        if target_id not in target_database:
            msg = 'Target "//%s" does not exist' % target_id
            dependent = _find_dependent(target_id, blade)
            (dependent or console).error(msg)
            continue

        related_targets[target_id] = target_database[target_id]
        for key in related_targets[target_id].deps:
            if key not in related_targets:
                cited_targets.add(key)

    return related_targets
