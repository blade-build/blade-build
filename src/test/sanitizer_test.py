# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration test for `--sanitizer=address` (#1038).

A cc_test with a heap-buffer-overflow passes normally (the OOB read returns
garbage) but is caught and fails under `--sanitizer=address`, which also
builds into the isolated `build64_release_asan` sibling dir.
"""


import os
import shutil

import blade_test


class TestSanitizerAsan(blade_test.TargetTest):
    """AddressSanitizer catches a bug the normal build misses."""

    ASAN_BUILD_DIR = 'build64_release_asan'

    def setUp(self):
        """setup method."""
        self.doSetUp('sanitizer', 'oob_test')
        shutil.rmtree(self.ASAN_BUILD_DIR, ignore_errors=True)

    def doTearDown(self):
        shutil.rmtree(self.ASAN_BUILD_DIR, ignore_errors=True)

    def testAsanCatchesHeapOverflow(self):
        # Without a sanitizer the OOB read is harmless -> the test passes.
        self.assertTrue(self.runBlade('test'),
                        'expected the un-sanitized test to pass')
        # Under ASan the same test is caught -> it fails.
        self.assertFalse(
            self.runBlade('test', '--sanitizer=address', print_error=False),
            'expected --sanitizer=address to catch the heap-buffer-overflow')
        # The sanitized build went to its own isolated dir.
        self.assertTrue(os.path.isdir(self.ASAN_BUILD_DIR),
                        'expected the %s build dir' % self.ASAN_BUILD_DIR)


class TestSanitizerUbsan(blade_test.TargetTest):
    """UBSan (made fatal) catches undefined behavior the normal build wraps."""

    UBSAN_BUILD_DIR = 'build64_release_ubsan'

    def setUp(self):
        """setup method."""
        self.doSetUp('sanitizer', 'ub_test')
        shutil.rmtree(self.UBSAN_BUILD_DIR, ignore_errors=True)

    def doTearDown(self):
        shutil.rmtree(self.UBSAN_BUILD_DIR, ignore_errors=True)

    def testUbsanCatchesSignedOverflow(self):
        # Normal build: the overflow wraps silently -> the test passes.
        self.assertTrue(self.runBlade('test'),
                        'expected the un-sanitized test to pass')
        # Under UBSan (fatal) the same test is caught -> it fails.
        self.assertFalse(
            self.runBlade('test', '--sanitizer=undefined', print_error=False),
            'expected --sanitizer=undefined to catch the signed overflow')
        self.assertTrue(os.path.isdir(self.UBSAN_BUILD_DIR),
                        'expected the %s build dir' % self.UBSAN_BUILD_DIR)


if __name__ == '__main__':
    blade_test.run(TestSanitizerAsan)
