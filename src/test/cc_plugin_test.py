# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
 This is the test module for cc_plugin target.

"""


import blade_test


class TestCcPlugin(blade_test.TargetTest):
    """Test cc_plugin."""
    def setUp(self):
        """setup method."""
        self.doSetUp('cc')

    def testGenerateRules(self):
        """Test that rules are generated correctly."""
        self.assertTrue(self.runBlade())

        com_lower_line = self.findCommand(['plowercase.cpp.o', '-c'])
        com_upper_line = self.findCommand(['puppercase.cpp.o', '-c'])
        com_string_line = self.findCommand(['string_plugin.cpp.o', '-c'])
        string_plugin_depends_libs = self.findCommand(['libstring_plugin.so'])

        self.assertCxxFlags(com_lower_line)
        self.assertCxxFlags(com_upper_line)
        self.assertCxxFlags(com_string_line)

        self.assertDynamicLinkFlags(string_plugin_depends_libs)
        self.assertIn('-Wl,-Bsymbolic', string_plugin_depends_libs)
        self.assertNotIn('liblowercase.a', string_plugin_depends_libs)
        self.assertNotIn('libuppercase.a', string_plugin_depends_libs)


if __name__ == '__main__':
    blade_test.run(TestCcPlugin)
