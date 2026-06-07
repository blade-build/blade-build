#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors
# All rights reserved.
#
# Unit tests for blade.console: progress bar drawing, throttling,
# terminal-width adaptation, and log file lifecycle.

"""Tests for :mod:`blade.console`.

The progress bar is the only piece of cursor-controlled UI in Blade. Bugs here
are highly visible (residue characters on screen, log files filled with escape
codes, lost output during concurrent prints) and easy to introduce by accident,
so we pin down the load-bearing invariants:

* every frame starts with ``\\r`` and ends with a clear-to-EOL escape, so that
  a shorter frame never leaves residue from a previous longer frame;
* the 100% frame is always painted even when it falls inside the throttle
  window of the previous redraw;
* the bar width tracks the terminal width without ever crossing the right
  edge (an over-wide line wraps, and a wrapped line breaks ``\\r`` redraw);
* writes from ``show_progress_bar`` and from ``_do_print`` are serialized so
  that messages never appear in the middle of a frame;
* ``set_log_file`` releases the previously held fd and registers the new one
  with ``atexit`` so the tail of the log is flushed on abnormal exit.
"""

import io
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import console  # noqa: E402


class _ConsoleStateMixin:
    """Save and restore module-level console state around each test.

    ``blade.console`` is intentionally a singleton — it matches the rest of
    Blade's runtime model — so tests have to discipline themselves about state
    leakage. Default state for each test: cursor control on, no prior frame,
    stdout/stderr captured into in-memory buffers.
    """

    def setUp(self):
        super().setUp()
        self._saved = {
            '_cursor_control': console._cursor_control,
            '_color_enabled': console._color_enabled,
            '_last_progress_value': console._last_progress_value,
            '_last_progress_time': console._last_progress_time,
            '_cursor_hidden': console._cursor_hidden,
            '_region_height': console._region_height,
            '_log': console._log,
        }
        console._cursor_control = True
        console._color_enabled = True
        console._last_progress_value = -1
        console._last_progress_time = 0
        console._cursor_hidden = False
        console._region_height = 0
        self._real_stderr = sys.stderr
        self._real_stdout = sys.stdout
        self.stderr = io.StringIO()
        self.stdout = io.StringIO()
        sys.stderr = self.stderr
        sys.stdout = self.stdout

    def tearDown(self):
        sys.stderr = self._real_stderr
        sys.stdout = self._real_stdout
        for k, v in self._saved.items():
            setattr(console, k, v)
        super().tearDown()


class ProgressBarFrameTest(_ConsoleStateMixin, unittest.TestCase):
    """A drawn frame must start with ``\\r`` and end with ``\\033[K``."""

    def test_frame_starts_with_cr_and_ends_with_clear_to_eol(self):
        # The "residue" bug — a previous, longer frame leaves tail characters
        # that the current shorter frame can't overwrite — is prevented by
        # leading \r (to ensure column 0) plus trailing \033[K (to wipe the
        # leftover tail). The hide-cursor escape sits in front of the \r but
        # doesn't affect the redraw geometry.
        console.show_progress_bar(5, 10)
        out = self.stderr.getvalue()
        # column 0 (\r) then the bar (grayscale blocks); trailing \033[K wipes
        # any leftover tail from a previous, longer frame.
        self.assertIn('\r' + console._GRAY_DONE, out,
                      f'expected CR + bar start inside the frame, got {out!r}')
        self.assertIn('5/10', out)
        self.assertTrue(out.endswith('\x1b[K'),
                        f'expected trailing \\033[K, got {out[-6:]!r}')

    def test_shorter_frame_emits_eol_clear_after_long_one(self):
        console.show_progress_bar(99, 100)
        # Defeat the dedup + throttle so the next call paints.
        console._last_progress_value = -1
        console._last_progress_time = 0
        console.show_progress_bar(1, 100)
        # Each frame must end with the clear sequence — that's what wipes the
        # leftover "9%" tail from the previous longer frame.
        self.assertEqual(self.stderr.getvalue().count('\x1b[K'), 2)

    def test_total_zero_does_not_crash(self):
        # total == 0 used to ZeroDivisionError on `current * 100 // total`.
        console.show_progress_bar(0, 0)
        console.show_progress_bar(5, 0)
        self.assertEqual(self.stderr.getvalue(), '')

    def test_no_output_without_cursor_control(self):
        # Non-tty (CI logs, piped output) must not get raw bar lines dumped
        # into them — the previous behavior of falling back to "\n" mode
        # produced unreadable log files.
        console._cursor_control = False
        for i in range(10):
            console.show_progress_bar(i, 10)
        self.assertEqual(self.stderr.getvalue(), '')


class ProgressBarRefreshLogicTest(_ConsoleStateMixin, unittest.TestCase):
    """Throttling, dedup, and the always-paint-100%-frame rule."""

    def test_same_value_is_deduped(self):
        console.show_progress_bar(5, 10)
        first = self.stderr.getvalue()
        console.show_progress_bar(5, 10)
        self.assertEqual(self.stderr.getvalue(), first,
                         'duplicate value should not redraw')

    def test_distinct_value_within_throttle_window_is_dropped(self):
        console.show_progress_bar(1, 100)
        # Immediately push a distinct value — still within the 200ms window.
        console.show_progress_bar(2, 100)
        self.assertEqual(self.stderr.getvalue().count('\r' + console._GRAY_DONE), 1,
                         'second frame within throttle window should be dropped')

    def test_100_percent_is_always_painted_even_when_throttled(self):
        # Without the current==total override, a build that races from 50% to
        # 100% inside 200ms would leave the user staring at "50%" forever.
        console.show_progress_bar(50, 100)
        console.show_progress_bar(100, 100)  # would normally be throttled
        self.assertIn('100/100', self.stderr.getvalue())


class ProgressBarWidthTest(unittest.TestCase):
    """``_compute_progress_bar_width`` must adapt to terminal size without
    crossing the right edge or shrinking below a usable minimum.
    """

    def _width_with_cols(self, cols, total):
        # shutil.get_terminal_size reads $COLUMNS / $LINES first, which lets
        # us pin terminal size deterministically without a pty.
        with patch.dict(os.environ, {'COLUMNS': str(cols), 'LINES': '24'}):
            return console._compute_progress_bar_width(total)

    def test_caps_at_max_for_wide_terminals(self):
        self.assertEqual(self._width_with_cols(200, 100),
                         console._MAX_PROGRESS_BAR_WIDTH)

    def test_shrinks_on_narrow_terminals(self):
        narrow = self._width_with_cols(40, 100)
        self.assertLess(narrow, console._MAX_PROGRESS_BAR_WIDTH)
        self.assertGreaterEqual(narrow, console._MIN_PROGRESS_BAR_WIDTH)

    def test_floors_at_min_on_pathologically_narrow_terminals(self):
        # 5-col terminals don't really exist, but the formatter must still
        # produce *something* renderable rather than crash or return <=0.
        self.assertEqual(self._width_with_cols(5, 100),
                         console._MIN_PROGRESS_BAR_WIDTH)

    def test_full_line_fits_strictly_within_terminal(self):
        # Invariant: total rendered line length is strictly less than the
        # reported terminal width. Hitting the right edge wraps the line,
        # which breaks the single-line \r redraw model.
        for cols in (40, 60, 80, 120):
            for total in (10, 100, 9999):
                with self.subTest(cols=cols, total=total):
                    with patch.dict(os.environ,
                                    {'COLUMNS': str(cols), 'LINES': '24'}):
                        # 100/100 is the longest numeric suffix possible.
                        line = console._progress_bar(100, total, total)
                        self.assertLess(
                            len(line), cols,
                            f'cols={cols} total={total}: line is '
                            f'{len(line)} chars: {line!r}')


class ClearProgressBarTest(_ConsoleStateMixin, unittest.TestCase):
    """``clear_progress_bar`` wipes the line, resets state, and is a no-op
    when there's nothing to clear."""

    def test_clears_after_a_drawn_frame(self):
        console.show_progress_bar(5, 10)
        self.stderr.truncate(0); self.stderr.seek(0)
        console.clear_progress_bar()
        # Minimal clear sequence: cursor to col 0, then EOL clear, then show
        # cursor (cursor was hidden while the bar was on screen).
        self.assertEqual(self.stderr.getvalue(), '\r\x1b[K\x1b[?25h')
        self.assertEqual(console._last_progress_value, -1)
        self.assertFalse(console._cursor_hidden)

    def test_noop_without_a_prior_frame(self):
        console.clear_progress_bar()
        self.assertEqual(self.stderr.getvalue(), '')

    def test_noop_when_cursor_control_disabled(self):
        # Even if _cursor_hidden gets stuck at True somehow (e.g. cursor
        # control was toggled off mid-build), we must not emit escape codes
        # into what is now a non-tty stream.
        console._cursor_control = False
        console._cursor_hidden = True
        console.clear_progress_bar()
        self.assertEqual(self.stderr.getvalue(), '')


class DoPrintClearsProgressBarTest(_ConsoleStateMixin, unittest.TestCase):
    """``_do_print`` is the join point that makes "errors scroll up, progress
    stays at the bottom" work — it must clear the progress bar before
    writing the message."""

    def test_clears_then_prints(self):
        console.show_progress_bar(5, 10)
        self.stderr.truncate(0); self.stderr.seek(0)
        self.stdout.truncate(0); self.stdout.seek(0)
        console._do_print('hello', file=sys.stderr)
        # Clear sequence + show-cursor first, then the message; nothing else.
        self.assertEqual(self.stderr.getvalue(), '\r\x1b[K\x1b[?25hhello\n')


class CursorVisibilityTest(_ConsoleStateMixin, unittest.TestCase):
    """Hide the cursor while a progress bar owns the bottom line; restore it
    before any non-progress output (or process exit) so the user never finds
    their terminal cursor-less."""

    def test_first_frame_emits_hide_cursor(self):
        console.show_progress_bar(5, 10)
        # The hide must come *before* the redraw, otherwise the blink is
        # visible for one frame.
        out = self.stderr.getvalue()
        self.assertTrue(out.startswith('\x1b[?25l'),
                        f'first frame must lead with hide-cursor, got {out[:8]!r}')
        self.assertTrue(console._cursor_hidden)

    def test_hide_cursor_emitted_only_once_across_redraws(self):
        # The hide is sticky: subsequent redraws inside the same "progress
        # active" stretch must not re-emit it, or the terminal sees a stream
        # of redundant escapes.
        console.show_progress_bar(1, 100)
        # Defeat dedup + throttle so the next draw really runs.
        console._last_progress_value = -1
        console._last_progress_time = 0
        console.show_progress_bar(2, 100)
        self.assertEqual(self.stderr.getvalue().count('\x1b[?25l'), 1)

    def test_clear_progress_bar_restores_cursor(self):
        console.show_progress_bar(5, 10)
        self.assertTrue(console._cursor_hidden)
        console.clear_progress_bar()
        self.assertFalse(console._cursor_hidden)
        self.assertIn('\x1b[?25h', self.stderr.getvalue())

    def test_no_cursor_escapes_without_cursor_control(self):
        # Non-tty must not see any cursor-visibility escapes either.
        console._cursor_control = False
        for i in range(5):
            console.show_progress_bar(i, 5)
        console.clear_progress_bar()
        self.assertNotIn('\x1b[?25', self.stderr.getvalue())
        self.assertFalse(console._cursor_hidden)

    def test_atexit_handler_restores_hidden_cursor(self):
        # Simulate "process exits while a frame is on screen": the cursor is
        # hidden and there's no clear_progress_bar before exit. The atexit
        # handler must emit a show.
        console.show_progress_bar(5, 10)
        self.assertTrue(console._cursor_hidden)
        # Don't reuse the show_progress_bar's stderr capture; the handler
        # should emit a new show-cursor escape.
        self.stderr.truncate(0); self.stderr.seek(0)
        console._restore_cursor_at_exit()
        self.assertEqual(self.stderr.getvalue(), '\x1b[?25h')

    def test_atexit_handler_is_noop_when_cursor_not_hidden(self):
        # Common case: build finishes cleanly, clear_progress_bar already ran,
        # nothing left to do. atexit must not emit a spurious show.
        self.assertFalse(console._cursor_hidden)
        console._restore_cursor_at_exit()
        self.assertEqual(self.stderr.getvalue(), '')


class ConcurrencyTest(_ConsoleStateMixin, unittest.TestCase):
    """The lock around the clear-then-write pair must keep concurrent
    progress refreshes and messages from interleaving inside a single
    frame's bytes."""

    def test_messages_never_split_a_progress_frame(self):
        # Run many progress redraws and many message prints in parallel.
        # With the lock, every frame ('\r' + bar-start ... '\033[K') must be a
        # contiguous, uninterrupted byte range — no message text in the
        # middle.
        with patch.object(console, '_PROGRESS_REFRESH_INTERVAL', 0):
            def producer_progress():
                for i in range(200):
                    # Force a distinct value so dedup doesn't drop it.
                    console.show_progress_bar(i % 99, 100)

            def producer_messages():
                for i in range(200):
                    console._do_print(f'msg-{i}', file=sys.stderr)

            t1 = threading.Thread(target=producer_progress)
            t2 = threading.Thread(target=producer_messages)
            t1.start(); t2.start(); t1.join(); t2.join()

        out = self.stderr.getvalue()
        # Walk the byte stream looking for frame starts. '\r' + the grayscale
        # "done" code marks a painted bar frame (a clear is '\r\033[K', whose
        # '\r' is followed by the EOL-clear, not the gray code). Between the
        # frame start and the next '\033[K' there must be no newline, otherwise
        # a message leaked into the frame.
        marker = '\r' + console._GRAY_DONE
        i = 0
        frames_seen = 0
        while True:
            start = out.find(marker, i)
            if start < 0:
                break
            end = out.find('\x1b[K', start)
            self.assertGreater(end, start,
                               'every frame must end with \\033[K')
            self.assertNotIn(
                '\n', out[start:end],
                f'message text leaked into frame: {out[start:end]!r}')
            frames_seen += 1
            i = end + 1
        self.assertGreater(frames_seen, 0,
                           'producer_progress should have emitted frames')


class LogFileLifecycleTest(_ConsoleStateMixin, unittest.TestCase):
    """``set_log_file`` releases any previously held fd and registers the
    new one with ``atexit`` so its tail is flushed on abnormal exit."""

    def test_re_setting_closes_previous_log(self):
        # We patch atexit so we don't leak handlers into the rest of the
        # test process. The functional behavior we care about here is just
        # the close-the-old-fd path.
        with tempfile.TemporaryDirectory() as td, \
                patch('blade.console.atexit'):
            console.set_log_file(os.path.join(td, 'a.log'))
            first = console._log
            console.set_log_file(os.path.join(td, 'b.log'))
            second = console._log
            self.assertTrue(first.closed,
                            'previous log fd must be released on re-set')
            self.assertFalse(second.closed)
            second.close()  # leave the fixture in a clean state

    def test_atexit_registers_a_closer_for_the_log(self):
        # We patch atexit.register to capture the callable rather than
        # actually register it for interpreter shutdown.
        with tempfile.TemporaryDirectory() as td, \
                patch('blade.console.atexit') as mock_atexit:
            console.set_log_file(os.path.join(td, 'a.log'))
            mock_atexit.register.assert_called_once()
            registered = mock_atexit.register.call_args[0][0]
            self.assertFalse(console._log.closed)
            registered()
            self.assertTrue(
                console._log.closed,
                'the atexit callable must close the current log file')


class VerbosityTest(unittest.TestCase):
    """Verbosity is an IntEnum. Callers now compare directly with ``>=`` / ``>``
    against ``Verbosity.X`` (see ninja_runner / workspace), or use the
    ``is_quiet()`` helper. Pin down: enum ordering, that ``set_verbosity`` still
    accepts both string names (the CLI used to produce them, and external callers
    may still) and enum values, and that ``is_quiet`` matches the only mode it
    names.
    """

    def setUp(self):
        super().setUp()
        self._saved_verbosity = console._verbosity

    def tearDown(self):
        console._verbosity = self._saved_verbosity
        super().tearDown()

    def test_enum_order_is_quiet_normal_verbose(self):
        # All caller-side comparisons (e.g. ``options.verbosity > QUIET``) depend
        # on this ordering, so it's the load-bearing invariant.
        self.assertLess(console.Verbosity.QUIET, console.Verbosity.NORMAL)
        self.assertLess(console.Verbosity.NORMAL, console.Verbosity.VERBOSE)

    def test_set_verbosity_accepts_string_name(self):
        # Kept for backward compatibility — external callers and tests may still
        # pass a raw string.
        console.set_verbosity('quiet')
        self.assertEqual(console.get_verbosity(), console.Verbosity.QUIET)
        console.set_verbosity('NORMAL')         # case-insensitive
        self.assertEqual(console.get_verbosity(), console.Verbosity.NORMAL)

    def test_set_verbosity_accepts_enum_directly(self):
        # Post-refactor callers (command_line.py argparse) hand us the enum.
        console.set_verbosity(console.Verbosity.VERBOSE)
        self.assertEqual(console.get_verbosity(), console.Verbosity.VERBOSE)

    def test_set_verbosity_rejects_unknown_name(self):
        # Bad input fails loud, not silent. The exact exception type is less
        # important than the fact that something is raised.
        with self.assertRaises((KeyError, ValueError)):
            console.set_verbosity('shouting')

    def test_is_quiet(self):
        # is_quiet() is _verbosity <= QUIET (not ==), matching the original
        # verbosity_le('quiet') it replaced. Today the two are equivalent because
        # QUIET is the lowest member; the distinction matters if a future SILENT
        # level (< QUIET) is ever added.
        console.set_verbosity(console.Verbosity.QUIET)
        self.assertTrue(console.is_quiet())
        console.set_verbosity(console.Verbosity.NORMAL)
        self.assertFalse(console.is_quiet())
        console.set_verbosity(console.Verbosity.VERBOSE)
        self.assertFalse(console.is_quiet())


if __name__ == '__main__':
    unittest.main()
