# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
 This is the test module for resource_library target.

"""


import blade_test


class TestResourceLibrary(blade_test.TargetTest):
    """Test resource_library."""
    def setUp(self):
        """setup method."""
        self.doSetUp('cc')

    def testGenerateRules(self):
        """Test that rules are generated correctly."""
        self.assertTrue(self.runBlade())
        com_lower_line = self.findCommand(['plowercase.cpp.o', '-c'])
        com_forms_line = self.findCommand(['forms.js.c.o', '-c'])
        com_poppy_line = self.findCommand(['poppy.html.c.o', '-c'])
        static_so_line = self.findCommand(['-shared', 'libstatic_resource.so'])
        lower_depends_libs = self.findCommand(['-shared', 'liblowercase.so'])
        gen_forms_line = self.findCommand(['forms.js.c', 'blade.builtin_tools resource'])
        gen_poppy_line = self.findCommand(['poppy.html.c', 'blade.builtin_tools resource'])

        self.assertTrue(gen_forms_line)
        self.assertTrue(gen_poppy_line)

        self.assertCxxFlags(com_lower_line)
        self.assertNoWarningCxxFlags(com_forms_line)
        self.assertNoWarningCxxFlags(com_poppy_line)

        self.assertDynamicLinkFlags(lower_depends_libs)


if __name__ == '__main__':
    blade_test.run(TestResourceLibrary)
