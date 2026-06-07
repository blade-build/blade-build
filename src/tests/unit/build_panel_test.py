#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Tests for the multi-line build progress panel: the tri-state grayscale bar,
ETA/truncation helpers, panel-line assembly, in-place redraw/clear escape
sequences, and the ninja status-line parser format.
"""

import io
import os
import re
import sys
import unittest
import unittest.mock as mock
from contextlib import redirect_stderr

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import console  # noqa: E402


class TriStateBarTest(unittest.TestCase):
    def test_segments_sum_to_width_no_color(self):
        with mock.patch.object(console, '_color_enabled', False):
            bar = console._tri_state_bar(2, 3, 10, 10)
        # 10 glyphs total: 2 done (█), 3 running (▒), 5 remaining (░)
        self.assertEqual(len(bar), 10)
        self.assertEqual(bar, '█' * 2 + '▒' * 3 + '░' * 5)

    def test_rounding_keeps_total_width(self):
        with mock.patch.object(console, '_color_enabled', False):
            for f in range(0, 8):
                for r in range(0, 8 - f):
                    bar = console._tri_state_bar(f, r, 7, 23)
                    self.assertEqual(len(bar), 23, (f, r))

    def test_color_uses_grayscale_ramp(self):
        with mock.patch.object(console, '_color_enabled', True):
            bar = console._tri_state_bar(1, 1, 4, 4)
        self.assertIn(console._GRAY_DONE, bar)
        self.assertIn(console._GRAY_RUNNING, bar)
        self.assertIn(console._GRAY_REMAINING, bar)
        self.assertTrue(bar.endswith(console._GRAY_RESET))


class HelperTest(unittest.TestCase):
    def test_format_eta(self):
        self.assertEqual(console._format_eta(None), '')
        self.assertEqual(console._format_eta(-1), '')
        self.assertEqual(console._format_eta(5), '  ETA 0:05')
        self.assertEqual(console._format_eta(125), '  ETA 2:05')
        self.assertEqual(console._format_eta(3725), '  ETA 1:02:05')

    def test_truncate(self):
        self.assertEqual(console._truncate('abc', 10), 'abc')
        self.assertEqual(console._truncate('abcdef', 4), 'abc…')
        self.assertEqual(console._truncate('abc', 0), '')


class PanelLinesTest(unittest.TestCase):
    def test_header_and_window(self):
        with mock.patch.object(console.shutil, 'get_terminal_size',
                               return_value=os.terminal_size((120, 40))), \
             mock.patch.object(console, '_color_enabled', False):
            lines = console._build_panel_lines(8, 2, 10, ['CC a.cc', 'CC b.cc'], 5)
        self.assertIn('8/10', lines[0])
        self.assertIn('80%', lines[0])
        self.assertIn('2 running', lines[0])
        self.assertIn('ETA 0:05', lines[0])
        self.assertEqual(lines[1:], ['  CC a.cc', '  CC b.cc'])

    def test_empty_window_is_header_only(self):
        # quiet mode passes an empty window -> just the aggregate bar line
        with mock.patch.object(console.shutil, 'get_terminal_size',
                               return_value=os.terminal_size((120, 40))), \
             mock.patch.object(console, '_color_enabled', False):
            lines = console._build_panel_lines(3, 1, 10, [], None)
        self.assertEqual(len(lines), 1)

    def test_window_capped_by_max(self):
        recent = ['step %d' % i for i in range(50)]
        with mock.patch.object(console.shutil, 'get_terminal_size',
                               return_value=os.terminal_size((120, 100))), \
             mock.patch.object(console, '_color_enabled', False):
            lines = console._build_panel_lines(50, 0, 50, recent, None)
        self.assertEqual(len(lines), 1 + console._PANEL_MAX_RECENT)  # header + cap
        self.assertEqual(lines[-1], '  step 49')                     # newest kept


class RenderClearTest(unittest.TestCase):
    def setUp(self):
        # reset module render state between tests
        console._region_height = 0
        console._cursor_hidden = False
        console._last_progress_time = 0

    def tearDown(self):
        # don't leak the singleton render state into other test modules
        console._region_height = 0
        console._cursor_hidden = False
        console._last_progress_time = 0

    def _render(self, **kw):
        buf = io.StringIO()
        with mock.patch.object(console, '_cursor_control', True), \
             mock.patch.object(console, '_color_enabled', False), \
             mock.patch.object(console.shutil, 'get_terminal_size',
                               return_value=os.terminal_size((120, 40))), \
             mock.patch.object(console.sys, 'stderr', buf), \
             redirect_stderr(buf):
            console.render_build_panel(**kw)
        return buf.getvalue()

    def test_first_render_sets_height_no_cursor_up(self):
        out = self._render(finished=1, running=1, total=3, recent=['a', 'b'])
        self.assertNotIn('\033[0A', out)
        self.assertNotIn('A', out.replace('ETA', ''))  # no cursor-up on first frame
        self.assertIn(console._CLEAR_TO_DISPLAY_END, out)
        self.assertEqual(console._region_height, 3)    # header + 2 recent

    def test_redraw_moves_cursor_up_by_prev_height(self):
        self._render(finished=3, running=0, total=3, recent=['a', 'b'])  # height 3
        out = self._render(finished=3, running=0, total=3, recent=['a', 'b', 'c'])
        self.assertIn('\033[3A', out)  # moved up by the previous panel height

    def test_clear_wipes_panel(self):
        self._render(finished=3, running=0, total=3, recent=['a', 'b'])  # height 3
        buf = io.StringIO()
        with mock.patch.object(console, '_cursor_control', True), \
             mock.patch.object(console.sys, 'stderr', buf):
            console.clear_progress_bar()
        self.assertIn('\033[3A', buf.getvalue())
        self.assertIn(console._CLEAR_TO_DISPLAY_END, buf.getvalue())
        self.assertEqual(console._region_height, 0)


class NinjaStatusFormatTest(unittest.TestCase):
    def test_parse_finished_total_running_desc(self):
        rx = re.compile(r'^\[(\d+)/(\d+)\]\((\d+)\)\s+(.*)$')
        m = rx.match('[12/100](4) CC foo/bar.cc')
        self.assertEqual(m.groups(), ('12', '100', '4', 'CC foo/bar.cc'))
        self.assertIsNone(rx.match('FAILED: [code=1] foo.o'))
        self.assertIsNone(rx.match('ninja: build stopped: subcommand failed.'))


if __name__ == '__main__':
    unittest.main()
