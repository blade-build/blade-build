# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Huan Yu <huanyu@tencent.com>
#         Feng chen <phongchen@tencent.com>
#         Yi Wang <yiwang@tencent.com>
#         Chong peng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
This is the util module which provides command functions.
"""


import atexit
import datetime
import enum
import os
import shutil
import sys
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import NoReturn

##############################################################################
# Color and screen
##############################################################################


def _windows_console_support_ansi_color():
    """Enable ANSI escape sequence processing on Windows console."""
    from ctypes import byref, windll, wintypes
    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    INVALID_HANDLE_VALUE = -1
    STD_OUTPUT_HANDLE = -11  # Win32 GetStdHandle id; defined locally so we don't depend on subprocess internals.

    handle = windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
    if handle == INVALID_HANDLE_VALUE:
        return False

    mode = wintypes.DWORD()
    if not windll.kernel32.GetConsoleMode(handle, byref(mode)):
        return False

    if not (mode.value & ENABLE_VIRTUAL_TERMINAL_PROCESSING):
        if windll.kernel32.SetConsoleMode(
            handle,
            mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING) == 0:
            print('kernel32.SetConsoleMode to enable ANSI sequences failed',
                file=sys.stderr)
    return True


def _console_support_ansi_color():
    if os.name == 'nt':
        return _windows_console_support_ansi_color()
    return sys.stdout.isatty() and os.environ.get('TERM') not in ('emacs', 'dumb')


def _console_support_cursor_control():
    """Whether the stream that carries the progress bar can interpret \\r and cursor escapes."""
    if os.name == 'nt':
        # On Windows, VTP gates both color and cursor escapes; if it's off, neither works.
        return _windows_console_support_ansi_color() and sys.stderr.isatty()
    return sys.stderr.isatty() and os.environ.get('TERM') not in ('emacs', 'dumb', '')


# Global color enabled or not
_color_enabled = _console_support_ansi_color()

# Whether the terminal supports cursor control (\r, \033[K, ...).
# Conceptually independent from color support, even if they coincide on most terminals.
_cursor_control = _console_support_cursor_control()

# Serializes writes to stdout/stderr so the progress bar and messages don't interleave.
_print_lock = threading.Lock()

# See http://en.wikipedia.org/wiki/ANSI_escape_code
# colors

# pylint: disable=bad-whitespace
_COLORS = {
    'red': '\033[1;31m',
    'green': '\033[1;32m',
    'yellow': '\033[1;33m',
    'blue': '\033[1;34m',
    'purple': '\033[1;35m',
    'cyan': '\033[1;36m',
    'white': '\033[1;37m',
    'gray': '\033[1;38m',
    'dimpurple': '\033[2;35m',
    'end': '\033[0m',
}

# Clears from the cursor to end of line. Always emit \r first so the cursor is at
# column 0 and the whole visible line is wiped, including any tail left by a
# previous, longer frame (e.g. "99/100 99%" -> "1/100 1%").
_CLEAR_TO_EOL = '\033[K'

# Cursor visibility. Hide while the progress bar owns the last line so the
# blinking block at the end of the bar doesn't sit there looking sloppy.
# The matching show MUST run no matter how the process exits — see the atexit
# and signal hooks at the bottom of this section.
_HIDE_CURSOR = '\033[?25l'
_SHOW_CURSOR = '\033[?25h'


def color_enabled():
    return _color_enabled


def enable_color(value):
    global _color_enabled
    _color_enabled = value


def color(name):
    """Return ansi console control sequence from color name"""
    if _color_enabled:
        return _COLORS[name]
    return ''


def colored(text, color):
    """Return ansi color code enclosed text"""
    if _color_enabled:
        return _COLORS[color] + text + _COLORS['end']
    return text


##############################################################################
# Log
##############################################################################


# Global log file for detailed output during build
_log = None


def set_log_file(log_file):
    """Set the global log file."""
    global _log
    if _log is not None:
        # Close any previously opened log to avoid leaking the file descriptor.
        _log.close()
    # File lifetime is process-wide on purpose; close is performed by the
    # atexit hook below (and by the re-set guard above on a subsequent call).
    _log = open(log_file, 'w', 1)  # lgtm[py/file-not-closed]
    atexit.register(_log.close)


def get_log_file():
    """Return the global log file name."""
    assert _log is not None, 'log file not set'
    return _log.name


def log(msg):
    """Dump message into log file."""
    if _log:
        timestamp = datetime.datetime.now().strftime('%F %T.%f')
        print(timestamp, msg, file=_log)


##############################################################################
# Verbosity
##############################################################################


class Verbosity(enum.IntEnum):
    """Output verbosity, ordered low to high.

    - QUIET: only show warnings and errors
    - NORMAL: show infos, warnings and errors
    - VERBOSE: show more details
    """
    QUIET = 0
    NORMAL = 1
    VERBOSE = 2


_verbosity = Verbosity.NORMAL


def _to_verbosity(value):
    """Coerce a Verbosity or a case-insensitive name to a Verbosity."""
    if isinstance(value, Verbosity):
        return value
    return Verbosity[value.upper()]


def set_verbosity(value):
    """Set the global verbosity. Accepts a Verbosity or a string name
    ('quiet' / 'normal' / 'verbose', case-insensitive)."""
    global _verbosity
    _verbosity = _to_verbosity(value)


def get_verbosity():
    return _verbosity


def verbosity_compare(lhs, rhs):
    """Return -1, 0, 1 according to their order."""
    a = _to_verbosity(lhs)
    b = _to_verbosity(rhs)
    return (a > b) - (a < b)


def verbosity_le(expected):
    """Current verbosity less than or equal to expected."""
    return _verbosity <= _to_verbosity(expected)


def verbosity_ge(expected):
    """Current verbosity greater than or equal to expected."""
    return _verbosity >= _to_verbosity(expected)


##############################################################################
# Progress bar
##############################################################################

# Sane bounds for the bar's filled-area width. Narrow terminals would otherwise
# get a wrap-around (which kills cursor-based redraw); very wide terminals would
# get a uselessly stretched bar.
_MIN_PROGRESS_BAR_WIDTH = 10
_MAX_PROGRESS_BAR_WIDTH = 60
# Throttle progress bar refresh. Short enough that the bar feels alive; long enough
# to avoid flooding the terminal when actions complete in bursts.
_PROGRESS_REFRESH_INTERVAL = 0.2

_last_progress_value = -1  # The last progress bar value, -1 means none
_last_progress_time = 0
# True iff a progress frame is currently on screen and we owe both a clear
# (\r + \033[K) and a show-cursor (\033[?25h). Tracks "there's a frame to wipe"
# and "we hid the cursor" together because those two facts are flipped in
# lockstep — see show_progress_bar.
_cursor_hidden = False


def _compute_progress_bar_width(total):
    """Pick a bar width that fits the current terminal, bounded by [MIN, MAX]."""
    cols = shutil.get_terminal_size((80, 24)).columns
    # Layout: "[<bar>] <current>/<total> <p>%". len(current) <= len(total) and
    # p ranges 0..100 (<=3 chars). Non-bar chars = 5 fixed + 2*len(total) + 3 = 8 + 2*len(total).
    # Add 1 column of margin so the line stays strictly under `cols`; hitting the
    # right edge would auto-wrap and break the single-line \r redraw.
    overhead = 9 + 2 * len(str(total))
    return max(_MIN_PROGRESS_BAR_WIDTH, min(_MAX_PROGRESS_BAR_WIDTH, cols - overhead - 1))


def _progress_bar(progress, current, total):
    """Progress bar drawing text, like this:
    [===========================================================----] 46/50 92%
    """
    bar_width = _compute_progress_bar_width(total)
    filled = progress * bar_width // 100
    return '[{}{}] {}/{} {:g}%'.format('=' * filled, '-' * (bar_width - filled),
                                  current, total, progress)


def _need_refresh_progress_bar(current, total, now):
    if _last_progress_value == current:
        return False
    if current == total:
        # Always paint the final 100% frame, even if it would otherwise be throttled away.
        return True
    return now - _last_progress_time >= _PROGRESS_REFRESH_INTERVAL


def _hide_cursor_locked():
    """Emit _HIDE_CURSOR exactly once per hide/show cycle. Caller holds _print_lock."""
    global _cursor_hidden
    if not _cursor_hidden:
        sys.stderr.write(_HIDE_CURSOR)
        _cursor_hidden = True


def show_progress_bar(current, total):
    global _last_progress_value, _last_progress_time
    if total <= 0 or not _cursor_control:
        # No real terminal -> don't dump repeated bar lines into a log file or pipe.
        return
    progress = current * 100 // total
    now = time.time()
    with _print_lock:
        if not _need_refresh_progress_bar(current, total, now):
            return
        _hide_cursor_locked()
        sys.stderr.write('\r' + _progress_bar(progress, current, total) + _CLEAR_TO_EOL)
        sys.stderr.flush()
        _last_progress_value = current
        _last_progress_time = now


def _clear_progress_bar_locked():
    """Erase the progress bar in place. Caller must hold _print_lock."""
    global _cursor_hidden, _last_progress_value, _last_progress_time
    if _cursor_hidden and _cursor_control:
        # Wipe the frame and hand the cursor back, in a single flush so that
        # any subsequent message lands on a clean line with a visible cursor.
        sys.stderr.write('\r' + _CLEAR_TO_EOL + _SHOW_CURSOR)
        sys.stderr.flush()
    _cursor_hidden = False
    _last_progress_value = -1
    _last_progress_time = 0


def clear_progress_bar():
    with _print_lock:
        _clear_progress_bar_locked()


def _restore_cursor_at_exit():
    """Ensure the cursor is visible no matter how the process exits.

    atexit covers normal exit, sys.exit, and exceptions propagating to the
    top of the stack (including KeyboardInterrupt from Ctrl+C). Without this
    hook, an interrupted Blade build would leave the user's terminal with no
    visible cursor until they ran ``reset`` or ``stty echo``.
    """
    if _cursor_hidden:
        try:
            sys.stderr.write(_SHOW_CURSOR)
            sys.stderr.flush()
        except (OSError, ValueError):
            # stderr may already be closed during interpreter shutdown.
            pass


if _cursor_control:
    atexit.register(_restore_cursor_at_exit)


##############################################################################
# Output
##############################################################################


def _do_print(msg, file=sys.stdout):
    # Hold the lock across "clear" and "print" so the progress refresh path can't
    # squeeze a redraw between them and split the message.
    with _print_lock:
        _clear_progress_bar_locked()
        print(msg, file=file)


def _print(msg, verbosity):
    if verbosity_ge(verbosity):
        _do_print(msg)


def output(msg):
    """Output message without any decoration"""
    _do_print(msg)
    log(msg)


# Global Error Counter
_error_count = 0


def error_count():
    """Return error log count"""
    return _error_count


def error(msg, prefix=True):
    """dump error message."""
    if prefix:
        msg = 'Blade(error): ' + msg
    log(msg)
    _do_print(colored(msg, 'red'), file=sys.stderr)
    global _error_count
    _error_count += 1


def fatal(msg: str, code: int = 1, prefix: bool = True) -> 'NoReturn':
    """dump error message and exit."""
    error(msg, prefix=prefix)
    sys.exit(code)


def warning(msg, prefix=True):
    """dump warning message."""
    if prefix:
        msg = 'Blade(warning): ' + msg
    log(msg)
    msg = colored(msg, 'yellow')
    _do_print(msg, file=sys.stderr)


def notice(msg, prefix=True):
    """dump notable message which is not a warning or error,
       visible in quiet mode"""
    if prefix:
        msg = 'Blade(notice): ' + msg
    log(msg)
    _print(colored(msg, 'blue'), 'quiet')


def info(msg, prefix=True):
    """dump info message."""
    if prefix:
        msg = 'Blade(info): ' + msg
    log(msg)
    _print(colored(msg, 'cyan'), 'normal')


def debug(msg, prefix=True):
    """dump debug message."""
    if prefix:
        msg = 'Blade(debug): ' + msg
    log(msg)
    _print(msg, 'verbose')


def diagnose(source_location, severity, message):
    """Output diagnostic message with source location and severity."""
    assert severity in ('debug', 'info', 'notice', 'warning', 'error')
    globals()[severity](f"{source_location}: {severity}: {message}", prefix=False)


def flush():
    sys.stdout.flush()
    sys.stderr.flush()
    if _log:
        _log.flush()
