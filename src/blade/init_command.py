# Copyright (c) 2026 The Blade Authors. All rights reserved.

"""Implementation of the `blade init` subcommand.

Create a starter ``BLADE_ROOT`` in the current directory, optionally with
commented configuration blocks for the requested languages, so a new
workspace can be set up with a single command.
"""

import os

from blade import console
from blade import util


# Accepted --lang aliases -> canonical key.
_LANG_ALIASES = {
    'cc': 'cc', 'c++': 'cc', 'cpp': 'cc', 'cxx': 'cc',
    'java': 'java',
    'scala': 'scala',
    'go': 'go', 'golang': 'go',
    'python': 'python', 'py': 'python',
    'proto': 'proto', 'protobuf': 'proto',
}

# Canonical languages, in the order they are emitted for `--lang=all`.
_ALL_LANGS = ['cc', 'java', 'scala', 'go', 'python', 'proto']

_LANG_TITLES = {
    'cc': 'C/C++', 'java': 'Java', 'scala': 'Scala',
    'go': 'Go', 'python': 'Python', 'proto': 'Protocol Buffers',
}

_HEADER = '''\
# BLADE_ROOT marks the root directory of a Blade workspace.
# Build targets are addressed relative to this directory as //path:name.
#
# It is also where workspace-wide build configuration lives. Everything
# below is commented out -- uncomment and edit only what you need.
# Full reference: https://github.com/blade-build/blade-build/blob/master/doc/en/config.md
'''

_GLOBAL_BLOCK = '''\
# global_config(
#     test_timeout = 600,                  # per-test timeout, seconds
#     duplicated_source_action = 'error',  # 'warning' | 'error' | 'none'
#     # build_jobs = 0,                    # 0 = auto (number of CPUs)
# )
'''

_LANG_BLOCKS = {
    'cc': '''\
# cc_config(
#     warnings = ['-Wall', '-Wextra'],
#     cxxflags = ['-std=c++20'],
#     optimize = ['-O2'],
# )
''',
    'java': '''\
# java_config(
#     version = '17',          # shorthand for source_version + target_version
#     # source_version = '17',
#     # target_version = '17',
# )
''',
    'scala': '''\
# scala_config(
#     # scala_home = '/path/to/scala',
#     source_encoding = 'UTF-8',
# )
''',
    'go': '''\
# go_config(
#     # go = 'go',                # the go command
#     go_module_enabled = True,
# )
''',
    'python': '''\
# Python targets need no workspace configuration by default.
# See the docs if you need to customize py_binary / py_test behaviour.
''',
    'proto': '''\
# proto_library_config(
#     # protoc = 'protoc',
#     # protobuf_libs = ['//path/to:protobuf'],
# )
''',
}


def parse_langs(spec):
    """Normalize a comma-separated --lang value into canonical languages.

    Returns an ordered, de-duplicated list (default ``['cc']``). Calls
    console.fatal (which exits) on an unknown language.
    """
    if not spec:
        return ['cc']
    result = []

    def add(lang):
        if lang not in result:
            result.append(lang)

    for raw in spec.split(','):
        name = raw.strip().lower()
        if not name:
            continue
        if name == 'all':
            for lang in _ALL_LANGS:
                add(lang)
            continue
        if name not in _LANG_ALIASES:
            console.fatal(
                "Unknown --lang '%s'. Choose from: %s (or 'all')." % (
                    raw, ', '.join(_ALL_LANGS)))
        add(_LANG_ALIASES[name])
    return result or ['cc']


def generate_blade_root(langs):
    """Return the text of a starter BLADE_ROOT for the given languages."""
    blocks = [_HEADER.rstrip(),
              '# --- Global ---\n' + _GLOBAL_BLOCK.rstrip()]
    for lang in langs:
        blocks.append('# --- %s ---\n' % _LANG_TITLES[lang] +
                      _LANG_BLOCKS[lang].rstrip())
    return '\n\n'.join(blocks) + '\n'


def run_init(options):
    """Create BLADE_ROOT in the current directory. Return an exit code.

    Refuses by default when the current directory is at or under an existing
    workspace, since that would create a nested workspace. --force skips the
    check (and overwrites a BLADE_ROOT already in this directory).
    """
    if not getattr(options, 'force', False):
        existing = util.find_file_bottom_up('BLADE_ROOT')
        if existing:
            root = os.path.dirname(existing)
            # realpath both sides so a /tmp -> /private/tmp style symlink
            # doesn't make "cwd is the root" look like a nested workspace.
            if os.path.realpath(root) == os.path.realpath('.'):
                console.error(
                    "'%s' already exists; this directory is already a workspace "
                    'root. Pass --force to overwrite.' % existing)
            else:
                console.error(
                    "This directory is already inside the workspace rooted at "
                    "'%s'; 'blade init' here would create a nested workspace. "
                    'Pass --force if that is intended.' % root)
            return 1
    langs = parse_langs(getattr(options, 'lang', None))
    path = 'BLADE_ROOT'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(generate_blade_root(langs))
    console.notice('Created %s (languages: %s)' % (
        os.path.abspath(path), ', '.join(langs)))
    return 0
