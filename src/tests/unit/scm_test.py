#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for SCM (git/svn) info generation in workspace.py.

"""SCM info is best-effort: a workspace under `.git`/`.svn` whose VCS tool is
not installed must degrade to 'unknown', not crash blade.

Regression for the case where `git`/`svn` is absent: `util.run_command`
raises `FileNotFoundError` (a subclass of `OSError`) when the binary is
missing, which previously propagated out of `setup_build_dir` and aborted the
whole build with a traceback.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import workspace  # noqa: E402


class ScmMissingToolTest(unittest.TestCase):
    """git/svn not installed => defaults, no exception."""

    def test_git_missing_returns_unknown(self):
        with mock.patch.object(workspace.util, 'run_command',
                               side_effect=FileNotFoundError(2, 'No such file', 'git')):
            url, revision = workspace._generate_scm_git()
        self.assertEqual(('unknown', 'unknown'), (url, revision))

    def test_svn_missing_returns_unknown(self):
        with mock.patch.object(workspace.util, 'run_command',
                               side_effect=FileNotFoundError(2, 'No such file', 'svn')):
            url, revision = workspace._generate_scm_svn()
        self.assertEqual(('unknown', 'unknown'), (url, revision))

    def test_generate_scm_does_not_raise_when_git_missing(self):
        """The end-to-end path `_generate_scm` (called from setup_build_dir)
        must not propagate the missing-tool error."""
        with mock.patch('os.path.isdir', side_effect=lambda p: p == '.git'), \
             mock.patch.object(workspace.util, 'run_command',
                               side_effect=FileNotFoundError(2, 'No such file', 'git')), \
             mock.patch.object(workspace, 'open', mock.mock_open(), create=True):
            # Should complete without raising.
            workspace._generate_scm('/tmp/nonexistent_build_dir_xyz')


class ScmSuccessTest(unittest.TestCase):
    """Normal path still parses revision/url."""

    def test_git_parses_revision_and_url(self):
        def fake_run(cmd, **kw):
            if cmd[:2] == ['git', 'rev-parse']:
                return 0, 'deadbeef\n', ''
            if cmd[:2] == ['git', 'remote']:
                return 0, 'origin\thttps://example.com/r.git (fetch)\n', ''
            return 1, '', 'err'
        with mock.patch.object(workspace.util, 'run_command', side_effect=fake_run):
            url, revision = workspace._generate_scm_git()
        self.assertEqual('deadbeef', revision)
        self.assertEqual('https://example.com/r.git', url)

    def test_git_strips_userinfo_from_url(self):
        def fake_run(cmd, **kw):
            if cmd[:2] == ['git', 'rev-parse']:
                return 0, 'abc123\n', ''
            return 0, 'origin\thttps://user:pass@example.com/r.git (fetch)\n', ''
        with mock.patch.object(workspace.util, 'run_command', side_effect=fake_run):
            url, _ = workspace._generate_scm_git()
        self.assertEqual('https://example.com/r.git', url)


if __name__ == '__main__':
    unittest.main()
