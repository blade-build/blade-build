#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.test_scheduler.

"""Unit tests for the test scheduler's timeout logic.

These tests pin down the documented semantics of
``global_config.test_timeout``: a value of 0 (or any non-positive value)
means *unlimited*, not "zero seconds". Without this contract the
scheduler's 1-second polling loop SIGTERMs every test as soon as it wakes
up, which is how it silently killed the java_basic smoke suite (JVM
startup happens to land on the second-boundary) while letting faster
cc_basic / py_basic tests escape because their subprocesses exited before
the first tick.
"""

import os
import sys
import unittest
from unittest import mock

# Make ``import blade.*`` resolve against the in-tree sources without
# requiring blade to be installed.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import test_scheduler  # noqa: E402  (sys.path tweak above)


def _make_worker(timeout, start_time=1000.0):
    """Build a WorkerThread pre-seeded with a fake running job.

    We bypass __init__ so the test does not need a real Queue/handler; we
    only care about the per-job bookkeeping that check_job_timeout reads.
    The job_process is a Mock so we can assert whether terminate() was
    called.
    """
    t = test_scheduler.WorkerThread.__new__(test_scheduler.WorkerThread)
    # Fields touched by check_job_timeout / set_job_data.
    import threading
    t.job_lock = threading.Lock()
    t.job_is_timeout = False
    t.job_start_time = start_time
    t.job_timeout = timeout
    t.job_name = 'some/target:test'
    t.job_process = mock.Mock()
    return t


def _terminate_mock(t):
    """Return the Mock for t.job_process.terminate, narrowed for pyright.

    ``WorkerThread.job_process`` is typed as Optional since it is reset to
    None by cleanup_job, but in these tests we always seed it with a Mock,
    so the assertions below are safe.
    """
    assert t.job_process is not None
    return t.job_process.terminate


class CheckJobTimeoutTest(unittest.TestCase):
    """Cover the timeout=0-means-unlimited contract at the worker level."""

    def test_zero_timeout_never_fires_even_far_in_the_future(self):
        # Regression pin: before the fix, `start_time + 0 < now` was True
        # for any now > start_time, so the very next scheduler tick (1s
        # later) would SIGTERM every running test.
        t = _make_worker(timeout=0, start_time=1000.0)
        t.check_job_timeout(now=1_000_000.0)  # 11+ days later
        self.assertFalse(t.job_is_timeout)
        _terminate_mock(t).assert_not_called()

    def test_negative_timeout_is_also_unlimited(self):
        # Defensive: any non-positive value means unlimited, so a
        # hand-edited BLADE config with a negative number should not
        # brick testing either.
        t = _make_worker(timeout=-5, start_time=1000.0)
        t.check_job_timeout(now=1_000_000.0)
        self.assertFalse(t.job_is_timeout)
        _terminate_mock(t).assert_not_called()

    def test_none_timeout_never_fires(self):
        # The caller in _wait_worker_threads is guarded, but belt-and-braces:
        # a None slipping through here must not crash or fire.
        t = _make_worker(timeout=None, start_time=1000.0)
        t.check_job_timeout(now=1_000_000.0)
        self.assertFalse(t.job_is_timeout)
        _terminate_mock(t).assert_not_called()

    def test_positive_timeout_fires_when_elapsed(self):
        # Sanity: the timeout machinery still works for finite limits.
        t = _make_worker(timeout=10, start_time=1000.0)
        t.check_job_timeout(now=1020.0)  # 20s elapsed, exceeds 10s
        self.assertTrue(t.job_is_timeout)
        _terminate_mock(t).assert_called_once()

    def test_positive_timeout_does_not_fire_before_elapsed(self):
        t = _make_worker(timeout=10, start_time=1000.0)
        t.check_job_timeout(now=1005.0)  # only 5s in
        self.assertFalse(t.job_is_timeout)
        _terminate_mock(t).assert_not_called()

    def test_already_timed_out_job_is_not_terminated_twice(self):
        # If the scheduler ticks again after a timeout was fired, we must
        # not re-terminate (the process may already be gone / reaped).
        t = _make_worker(timeout=10, start_time=1000.0)
        t.job_is_timeout = True  # pretend a previous tick already fired
        t.check_job_timeout(now=1020.0)
        _terminate_mock(t).assert_not_called()


class ConfigDefaultTest(unittest.TestCase):
    """Pin the default value so the scheduler fix stays coherent with config."""

    def test_default_test_timeout_is_zero(self):
        # If someone changes the default to a small positive number later,
        # the scheduler-level fix (0 == unlimited) still holds, but the
        # surprise factor goes up: fail loud so a reviewer re-examines the
        # contract.
        from blade import config
        c = config.BladeConfig()
        self.assertEqual(c.configs['global_config']['test_timeout'], 0)


if __name__ == '__main__':
    unittest.main()
