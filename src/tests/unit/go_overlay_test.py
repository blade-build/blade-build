#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the `go_overlay` builtin (#1405 proto->Go overlay).

`generate_go_overlay` writes the JSON map consumed by `go build -overlay`.
Blade generates each `.pb.go` under the build dir (out of the source tree); the
overlay maps that file's **virtual** in-module location (its build_dir-relative
path) to its **actual** build_dir path, so a module-mode `go build` resolves it
as if it were checked in beside the `.proto`. Both sides are absolute so the map
survives `go -C <module_dir>` changing the working directory.
"""

import json
import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import builtin_tools  # noqa: E402  (sys.path tweak above)


class GenerateGoOverlayTest(unittest.TestCase):
    def _overlay(self, files, build_dir):
        """Run the builtin in a fresh cwd. Returns (parsed_json, base_dir),
        where base_dir is the (resolved) cwd the builtin saw -- so the caller
        can reconstruct the absolute paths it produced."""
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)
            try:
                base = os.getcwd()  # resolved (mkdtemp dir may be a symlink)
                out = 'x.overlay.json'
                builtin_tools.generate_go_overlay(files, out=out, build_dir=build_dir)
                with open(out, encoding='utf-8') as f:
                    return json.load(f), base
            finally:
                os.chdir(cwd)

    def test_maps_stripped_virtual_to_build_dir_actual(self):
        data, base = self._overlay(
            ['build64_release/pb/msg.pb.go', 'build64_release/api/svc.pb.go'],
            'build64_release')
        # Top-level shape is exactly {"Replace": {...}}.
        self.assertEqual(['Replace'], list(data.keys()))
        replace = data['Replace']
        self.assertEqual(2, len(replace))
        # virtual (build_dir prefix stripped) -> actual (the build_dir path).
        self.assertEqual(
            os.path.join(base, 'build64_release/pb/msg.pb.go'),
            replace[os.path.join(base, 'pb/msg.pb.go')])
        self.assertEqual(
            os.path.join(base, 'build64_release/api/svc.pb.go'),
            replace[os.path.join(base, 'api/svc.pb.go')])

    def test_both_sides_are_absolute(self):
        # `go -C <module_dir>` moves the cwd, so relative overlay paths would
        # break -- every key and value must be absolute.
        data, _ = self._overlay(['build64_release/pb/msg.pb.go'], 'build64_release')
        for virtual, actual in data['Replace'].items():
            self.assertTrue(os.path.isabs(virtual), virtual)
            self.assertTrue(os.path.isabs(actual), actual)

    def test_trailing_slash_on_build_dir_is_tolerated(self):
        # The prefix is stripped whether or not build_dir carries a trailing '/'.
        data, base = self._overlay(['build64_release/pb/msg.pb.go'], 'build64_release/')
        self.assertIn(os.path.join(base, 'pb/msg.pb.go'), data['Replace'])

    def test_file_outside_build_dir_keeps_its_path_as_virtual(self):
        # Defensive: a path not under build_dir is not stripped, so virtual and
        # actual coincide (no bogus prefix removal).
        data, base = self._overlay(['gen/pb/msg.pb.go'], 'build64_release')
        virtual = os.path.join(base, 'gen/pb/msg.pb.go')
        self.assertEqual(virtual, list(data['Replace'])[0])
        self.assertEqual(virtual, data['Replace'][virtual])


if __name__ == '__main__':
    unittest.main()
