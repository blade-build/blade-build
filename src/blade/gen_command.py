# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Shared command machinery for gen_rule and custom rules (#1204, #829).

Platform command selection + wrapping (cmd_bat / cmd_bash / raw) and the
gen_rule-style variable expansion ($SRCS / $OUTS / $OUTS[i] / $FIRST_* /
$SRC_DIR / ...). Extracted from gen_rule_target so custom_rule_target can reuse
it; gen_rule_target delegates here with no change in generated output.
"""

import os
import re

# $OUTS[i] / $OUTS[name] / $SRCS[i] / $SRCS[name] -- reference a single output or
# input by index (all-digits) or by declared name / basename.
OUTS_INDEX_RE = re.compile(r'\$OUTS\[([^\]]+)\]')
SRCS_INDEX_RE = re.compile(r'\$SRCS\[([^\]]+)\]')


def select_command(cmd, cmd_bash, cmd_bat):
    """Pick the command + how to run it for the host platform (issue #1204).

      * Windows: only cmd.exe -- ``cmd_bat`` preferred, then the generic ``cmd``.
      * POSIX: ``cmd_bash`` (run via bash) preferred, then the generic ``cmd``.

    No bash auto-detection on Windows -- it was fragile and hurt build
    stability. To use bash on Windows, run blade under a POSIX environment
    (WSL / msys2 / cygwin), or invoke ``bash -c "..."`` yourself inside
    ``cmd_bat``. Returns ``(command, kind, bash)`` with kind in
    ``{'bat','bash','raw'}``; ``(None, None, None)`` if nothing usable here.
    """
    if os.name == 'nt':
        if cmd_bat:
            return cmd_bat, 'bat', None
        if cmd:
            return cmd, 'raw', None
    else:
        if cmd_bash:
            return cmd_bash, 'bash', 'bash'
        if cmd:
            return cmd, 'raw', None
    return None, None, None


def index_ref(sel, names, paths, what, error):
    """Resolve a single $OUTS[sel] / $SRCS[sel] to one concrete path.

    ``sel`` is an index when all-digits, else a declared name or basename.
    ``error`` is a callable(msg) used to report a bad index/name.
    """
    if sel.isdigit():
        i = int(sel)
        if 0 <= i < len(paths):
            return paths[i]
        error('$%s index out of range: [%s]' % (what.upper(), sel))
        return ''
    for i, n in enumerate(names):
        if n == sel or os.path.basename(n) == sel:
            return paths[i]
    error('$%s has no entry named "%s"' % (what.upper(), sel))
    return ''


def expand_vars(cmd, *, bash, src_names, src_paths, out_names, out_paths,
                path, build_dir, error, first_vars=True):
    """Expand the gen_rule command variables.

    For the bash kind all paths use '/' and $SRCS/$OUTS/$FIRST_* are substituted
    as concrete paths (ninja ${in}/${out} would render with backslashes on
    Windows, which bash treats as escapes); cmd/raw keep the ninja vars.

    ``first_vars`` controls the deprecated ``$FIRST_SRC`` / ``$FIRST_OUT``: gen_rule
    keeps them for back-compat, custom rules pass ``first_vars=False`` (use
    ``$SRCS[0]`` / ``$OUTS[0]`` instead).
    """
    def _p(p):
        return p.replace('\\', '/') if bash else p
    # Indexed/named refs first: a bare `$OUTS` replace below would otherwise
    # turn `$OUTS[0]` into `${out}[0]`.
    cmd = OUTS_INDEX_RE.sub(
        lambda m: _p(index_ref(m.group(1), out_names, out_paths, 'outs', error)), cmd)
    cmd = SRCS_INDEX_RE.sub(
        lambda m: _p(index_ref(m.group(1), src_names, src_paths, 'srcs', error)), cmd)
    if bash:
        cmd = cmd.replace('$SRCS', ' '.join(_p(i) for i in src_paths))
        cmd = cmd.replace('$OUTS', ' '.join(_p(o) for o in out_paths))
        if first_vars:
            cmd = cmd.replace('$FIRST_SRC', _p(src_paths[0]) if src_paths else '')
            cmd = cmd.replace('$FIRST_OUT', _p(out_paths[0]) if out_paths else '')
    else:
        cmd = cmd.replace('$SRCS', '${in}')
        cmd = cmd.replace('$OUTS', '${out}')
        if first_vars:
            cmd = cmd.replace('$FIRST_SRC', '${_in_1}')
            cmd = cmd.replace('$FIRST_OUT', '${_out_1}')
    cmd = cmd.replace('$SRC_DIR', _p(path))
    cmd = cmd.replace('$OUT_DIR', _p(os.path.join(build_dir, path)))
    cmd = cmd.replace('$BUILD_DIR', _p(build_dir))
    return cmd


def output_check(shell, outputs, root_dir):
    """A command that fails the build if any declared output is missing (#1204).

    Absolute paths so the check is immune to any `cd` the user command did.
    """
    outs = [os.path.join(root_dir, o) for o in outputs]
    if shell == 'cmd':
        return ' && '.join('if not exist "%s" exit /b 1' % o for o in outs)
    # sh/bash: forward slashes so backslashes aren't treated as escapes
    return ' && '.join('test -e "%s"' % o.replace('\\', '/') for o in outs)


def wrap_command(cmd, kind, bash, outputs, root_dir):
    """Wrap the user command with the right interpreter + output check (#1204).

    Launch arguments follow Bazel: ``cmd.exe /S /E:ON /V:ON /D /c`` for bat,
    ``bash -c`` with ``set -e -o pipefail`` for bash.
    """
    if kind == 'bash':
        inner = 'set -e -o pipefail;%s && %s' % (cmd, output_check('sh', outputs, root_dir))
        # single-quote the bash script so the double-quoted paths in the
        # output check don't clash with bash -c's own quoting.
        return '"%s" -c \'%s\'' % (bash, inner)
    if kind == 'bat' or os.name == 'nt':
        # On Windows wrap in an explicit cmd.exe (Bazel's launch args). This
        # also gives ninja a clean outer process to pipe -- a raw command doing
        # its own `>` redirection in ninja's directly-piped cmd can trip
        # "ninja: fatal: GetOverlappedResult".
        return 'cmd /S /E:ON /V:ON /D /c "%s && %s"' % (cmd, output_check('cmd', outputs, root_dir))
    # raw on POSIX: the host's /bin/sh -c runs it directly.
    return '%s && %s' % (cmd, output_check('sh', outputs, root_dir))
