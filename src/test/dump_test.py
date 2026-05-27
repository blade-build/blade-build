# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>
# Date:   Feb 12, 2012


"""
This is the test module to test dump function of blade.
"""

import json
import os
import blade_test


class TestDump(blade_test.TargetTest):
    def setUp(self):
        self.doSetUp('cc', target='...')

    def doTearDown(self):
        self.removeFile('blade-bin/dump.config')
        self.removeFile('blade-bin/compdb.json')
        self.removeFile('blade-bin/targets.json')

    def testDumpConfig(self):
        self.assertTrue(self.runBlade('dump', '--config'))
        self.assertTrue(self.runBlade('dump', '--config --to-file=blade-bin/dump.config'))
        self.assertTrue(os.path.isfile('blade-bin/dump.config'))


    def testDumpCompdb(self):
        self.assertTrue(self.runBlade('dump', '--compdb'))
        self.assertTrue(self.runBlade('dump', '--compdb --to-file=blade-bin/compdb.json'))
        json.load(open('blade-bin/compdb.json', encoding='utf-8'))

    def testDumpTargets(self):
        self.assertTrue(self.runBlade('dump', '--targets'))
        self.assertTrue(self.runBlade('dump', '--targets  --to-file=blade-bin/targets.json'))
        json.load(open('blade-bin/targets.json', encoding='utf-8'))

if __name__ == '__main__':
    blade_test.run(TestDump)
