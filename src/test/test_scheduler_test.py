# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>

"""Tests for ``test_scheduler.TestScheduler``."""

import unittest

import blade_test  # noqa: F401  -- adds src/blade to sys.path
from blade.test_scheduler import TestScheduler


class EffectiveTimeoutTest(unittest.TestCase):
    """``_effective_timeout`` -- run-time multiplier applied to per-target timeout."""

    def _scheduler(self, multiplier):
        return TestScheduler(tests_list=[], num_jobs=1,
                             test_timeout_multiplier=multiplier)

    def testDefaultMultiplierIsIdentity(self):
        s = self._scheduler(multiplier=1.0)
        self.assertEqual(s._effective_timeout(60), 60)

    def testMultiplierScales(self):
        s = self._scheduler(multiplier=3.0)
        self.assertEqual(s._effective_timeout(60), 180)

    def testZeroBaseStaysUnlimited(self):
        # 0 is the documented "unlimited" sentinel of global_config.test_timeout.
        # No multiplier should ever turn unlimited into limited.
        s = self._scheduler(multiplier=3.0)
        self.assertEqual(s._effective_timeout(0), 0)

    def testNegativeBaseStaysUnlimited(self):
        # config docstring: "0 (default) or any non-positive value means unlimited"
        s = self._scheduler(multiplier=2.0)
        self.assertEqual(s._effective_timeout(-1), -1)

    def testNoneBaseStaysNone(self):
        # target.attr.get('test_timeout') can return None on targets that
        # predate the attribute being set.
        s = self._scheduler(multiplier=2.0)
        self.assertIsNone(s._effective_timeout(None))

    def testFractionalMultiplier(self):
        s = self._scheduler(multiplier=0.5)
        self.assertEqual(s._effective_timeout(60), 30)


if __name__ == '__main__':
    blade_test.run(EffectiveTimeoutTest)
