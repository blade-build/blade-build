#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the `go` builtin wrapper (builtin_tools.generate_go).

The Go rules run go through this wrapper instead of a shell env-var prefix
(`GOPATH=x CGO_...=y go ...`), which is POSIX-only and breaks under cmd.exe on
Windows. The wrapper takes the env as base64(JSON) and the go command as
positional args, sets the env, runs go, and optionally touches a stamp output.
See the go-on-Windows port (issue #1369 follow-up).
"""

import base64
import json
import os
import sys
import tempfile
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import builtin_tools  # noqa: E402


def _b64(env):
    return base64.b64encode(json.dumps(env).encode('utf-8')).decode('ascii')


class GenerateGoTest(unittest.TestCase):
    def _run(self, args, envb64='', touch='', rc=0):
        with mock.patch.object(builtin_tools.subprocess, 'call',
                               return_value=rc) as call:
            result = builtin_tools.generate_go(args, envb64=envb64, touch=touch)
        return result, call

    def test_runs_the_command_after_double_dash(self):
        _, call = self._run(['--', 'go', 'build', './x'])
        self.assertEqual(['go', 'build', './x'], call.call_args[0][0])

    def test_no_double_dash_is_fine(self):
        _, call = self._run(['go', 'version'])
        self.assertEqual(['go', 'version'], call.call_args[0][0])

    def test_envb64_is_applied_to_child_env(self):
        env = {'GOPATH': '/gp', 'CGO_CFLAGS': '-I/a -I/b', 'CGO_ENABLED': '1'}
        _, call = self._run(['--', 'go', 'build'], envb64=_b64(env))
        passed = call.call_args[1]['env']
        self.assertEqual('/gp', passed['GOPATH'])
        self.assertEqual('-I/a -I/b', passed['CGO_CFLAGS'])  # spaces survive
        # Ambient env is preserved, not replaced.
        self.assertIn('PATH', passed)

    def test_empty_envb64_uses_ambient_env(self):
        _, call = self._run(['--', 'go', 'test'], envb64='')
        self.assertIn('PATH', call.call_args[1]['env'])

    def test_touch_creates_stamp_on_success(self):
        with tempfile.TemporaryDirectory() as d:
            stamp = os.path.join(d, 'stamp')
            rc, _ = self._run(['--', 'go', 'build'], touch=stamp, rc=0)
            self.assertEqual(0, rc)
            self.assertTrue(os.path.exists(stamp))

    def test_touch_skipped_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            stamp = os.path.join(d, 'stamp')
            rc, _ = self._run(['--', 'go', 'build'], touch=stamp, rc=1)
            self.assertEqual(1, rc)
            self.assertFalse(os.path.exists(stamp))

    def test_registered_as_builtin(self):
        self.assertIs(builtin_tools._BUILTIN_TOOLS['go'],
                      builtin_tools.generate_go)


if __name__ == '__main__':
    unittest.main()
