# The console: the build progress panel and the ninja status pipeline

`console.py` owns all of Blade's terminal decoration — colors, the cursor, and
the live **build progress panel**. The interesting part is how that panel is
driven: stock ninja exposes no structured progress API, so Blade reconstructs
the panel from ninja's plain status text. This note explains that pipeline.

| File | Role |
| --- | --- |
| `src/blade/console.py` | Color, cursor, the progress panel renderer + clear path |
| `src/blade/ninja_runner.py` | Runs ninja, captures its output, parses the status stream |
| `src/blade/ninja_rule.py` | `NinjaRule.emit()` — bakes the (colored) `description` into each rule |
| `src/blade/gen_rule_target.py`, `src/blade/windows_resources_target.py` | Per-target local rules; must color their own `description` |

## 1. Why parse ninja's stdout (and not an event API)

Ninja has **no** structured progress channel in the upstream tree. The protobuf
"frontend" interface (ninja PR #1210) was never merged, and bundling a fork just
for it isn't worth a protobuf dependency. So the only live signal is ninja's
status text.

Two facts about that text (see ninja `src/status_printer.cc`) shape the design:

- **Smart terminal**: ninja prints a status line on edge *start* and *finish*,
  overwriting in place with `\r`, and leaves the last line on screen — this is
  the leftover `[226/226] LINK …` line Blade used to show.
- **Piped / dumb** (what Blade uses): ninja prints **only on edge finish**, one
  line per completed edge, newline-terminated — and a separate `FAILED:` /
  `ninja: …` block on error. Edge *starts* are not printed.

So when Blade pipes ninja, it gets a clean, parseable stream: one
`[finished/total](running) <desc>` per completion, plus distinct error blocks.
The format is fixed by `NINJA_STATUS='[%f/%t](%r) '` (`%f`/`%t`/`%r` =
finished/total/running). Because dumb mode is finish-only, Blade can show the
**count** of running edges (`%r`) but not *which* edges are running — the
per-running-task identity would require the (unavailable) frontend protocol.

## 2. Two run modes (`ninja_runner._run_ninja_build`)

- **Verbose** (`-v`): hand the terminal straight to ninja
  (`_run_ninja_command`) so every command is printed in full. No panel.
- **Otherwise** (default + quiet): redirect ninja's stdout+stderr to
  `blade-bin/ninja_output.log` and tail it with `_show_progress`. Redirecting is
  what puts ninja in dumb mode, giving the finish-only stream above.

## 3. The parse loop (`ninja_runner._show_progress`)

A single reader loop classifies each line:

- Matches `^\[(\d+)/(\d+)\]\((\d+)\)\s+(.*)$` → a completed edge: update
  finished/total/running, push the description into a bounded
  `deque(maxlen=_PANEL_MAX_RECENT)`, compute ETA, and call
  `console.render_build_panel(...)`. (`%r` is decremented by one — ninja prints
  the finishing edge before decrementing its running counter.)
- Anything else → `console.output(line)`: a **permanent** line (warnings,
  errors, `ninja: …`). Leading indentation is preserved.
- On exit: clear the panel; on clean success print `"<N> build steps
  completed"`, which replaces the panel — no leftover `[N/N]` line.

## 4. Transient panel vs permanent output

The whole design rests on one split:

- The **panel** is *transient* — it lives at the bottom of the screen and is
  redrawn / erased in place.
- Everything else is *permanent* — printed with a trailing newline so it scrolls
  up and stays.

`console.output()` → `_do_print()` calls `_clear_progress_bar_locked()` **before**
printing. So when an error/warning arrives, the panel is wiped first, the message
is printed permanently above, and the next progress line repaints the panel below
it. Consequently **only Blade's own panel is ever erased — a real error is never
overwritten.** This is what makes "the last line might be an error" a non-issue.

## 5. Rendering the panel (`console.render_build_panel`)

The panel is a list of lines: a header (the bar) + the recent-completions window.
Drawing in place:

- Track `_region_height` = lines currently on screen.
- To redraw: move the cursor up `_region_height` lines (`\033[{n}A`), then
  `\r\033[J` (carriage return + clear-to-end-of-display) wipes the old panel and
  anything below, then print the new lines and park the cursor on the empty line
  *below* the panel — so the next redraw moves up exactly `_region_height`.
- The cursor is hidden while the panel is on screen (`_hide_cursor_locked`) and
  restored on clear and via an `atexit` hook, so an interrupted build never
  leaves the terminal cursorless.
- Repaints are throttled (`_PROGRESS_REFRESH_INTERVAL`), but the final 100% frame
  always paints.

The clear path is unified: `_clear_progress_bar_locked()` wipes the multi-line
panel when `_region_height > 0`, else the single-line bar (`\r` + clear-to-EOL).
Both also re-show the cursor.

## 6. The tri-state grayscale bar (`console._tri_state_bar`)

`%f`/`%r`/`%t` give three zones: **done** (finished), **running**, and
**remaining** (`total - finished - running`). The bar paints them in three
grayscale shades — bright / mid / dark (`\033[38;5;{252,245,238}m` block glyphs)
— so the build state reads at a glance. Segment widths use a **cumulative floor**
so they always sum to the bar width exactly:

```python
done_w = width * finished // total
run_w  = width * (finished + running) // total - done_w
rem_w  = width - done_w - run_w
```

When color is off, it falls back to distinct block glyphs (`█` / `▒` / `░`). The
bar width is sized so the header (`finished/total pct% ·running running  ETA …`)
fits one line; the recent-window lines are truncated to the terminal width — both
matter because a wrapped line would break the cursor-up math.

## 7. Rule descriptions are colored at generation time

What shows after `[N/N]` is the rule's ninja `description`, expanded by ninja.
Color is baked into that string **when the ninja file is generated**, not at
print time: `NinjaRule.emit()` wraps it in `console.colored(desc, 'dimpurple')`
(which returns plain text when color is off). Per-target *local* rules must do
the same, or they show up uncolored in the panel while every other step is
colored — this is why `gen_rule` and `windows_resources` (the `RC` rule) color
their own `description`.

## 8. Degradation

- **Non-TTY / redirected** (`_cursor_control` false): `render_build_panel` is a
  no-op — no escape codes leak into a pipe or log; only permanent lines + the
  summary appear.
- **Color off** (`_color_enabled` false): the bar uses glyph shades and
  descriptions are plain.
- **Quiet** (`is_quiet()`): the recent-completions window is dropped — only the
  aggregate bar is shown, no per-step descriptions.
- **Verbose**: no panel at all; ninja owns the terminal.
