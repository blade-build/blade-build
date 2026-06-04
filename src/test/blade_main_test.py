# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


"""
 This is the main test module for all targets.

"""


import sys
import unittest

from cc_binary_test import TestCcBinary
from cc_library_test import TestCcLibrary
from cc_plugin_test import TestCcPlugin
from cc_test_test import TestCcTest
from dsl_api_test import GetenvTest
from dump_test import TestDump
from system_include_test import (
    DeclareHdrsVirtualPathTest,
    ExportIncsListTest,
    GetCcFlagsTest,
    GetIncsListTest,
)
from test_scheduler_test import EffectiveTimeoutTest
from extension_test import TestExtension
from gen_rule_test import TestGenRule
from hdr_dep_check_test import TestHdrDepCheck
from java_test import TestJava
from lex_yacc_test import TestLexYacc
from proto_library_test import TestProtoLibrary
from prebuild_cc_library_test import TestPrebuildCcLibrary
from query_target_test import TestQuery
from resource_library_test import TestResourceLibrary
from target_pattern_test import TargetPatternTest
from linker_scripts_test import LinkerScriptsTest

from html_test_runner import HTMLTestRunner
from test_target_test import TestTestRunner


def _main():
    """main method."""
    suite_test = unittest.TestSuite()
    suite_test.addTests([
        unittest.defaultTestLoader.loadTestsFromTestCase(TargetPatternTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCcLibrary),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCcBinary),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCcPlugin),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestCcTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(DeclareHdrsVirtualPathTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(EffectiveTimeoutTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(ExportIncsListTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(GetCcFlagsTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(GetIncsListTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(GetenvTest),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestDump),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestExtension),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestGenRule),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestHdrDepCheck),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestJava),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestLexYacc),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestProtoLibrary),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestResourceLibrary),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestQuery),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestTestRunner),
        unittest.defaultTestLoader.loadTestsFromTestCase(TestPrebuildCcLibrary),
        unittest.defaultTestLoader.loadTestsFromTestCase(LinkerScriptsTest),
        ])

    generate_html = len(sys.argv) > 1 and sys.argv[1].startswith('html')
    if generate_html:
        runner = HTMLTestRunner(title='Blade unit test report')
        result = runner.run(suite_test)
    else:
        runner = unittest.TextTestRunner()
        result = runner.run(suite_test)

    if not result.wasSuccessful():
        sys.exit(1)


if __name__ == '__main__':
    _main()
