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
from build_from_subdir_test import BuildFromSubdirTest
from root_command_test import RootCommandTest
from deprecated_dep_test import TestDeprecatedDep
from cc_coverage_test import TestCcCoverage
from go_coverage_test import TestGoCoverage
from py_coverage_test import TestPyCoverage
from sanitizer_test import TestSanitizerAsan, TestSanitizerUbsan, TestSanitizerTsan
# Previously omitted from the suite (they only ran when invoked by hand); wired
# in below. A guard test (tests/unit/integration_suite_coverage_test.py) now
# fails if any src/test/*_test.py class is left out.
from go_build_test import (
    TestGoBinary,
    TestGoLibrary,
    TestSubdirModule,
    TestCgo,
    TestGoUnconfigured,
)
from guard_suppression_test import TestGuardSuppression
from header_only_incstk_test import TestHeaderOnlyIncstk
from tags_test import TagsTest

from html_test_runner import HTMLTestRunner
from test_target_test import TestTestRunner


# Every integration TestCase CI runs. Keep this exhaustive: the guard test
# tests/unit/integration_suite_coverage_test.py fails if any src/test/*_test.py
# class with `test*` methods is missing here, so a new test can't be silently
# dropped from CI (the bug this list caused before).
TEST_CASES = [
    TargetPatternTest,
    TestCcLibrary,
    TestCcBinary,
    TestCcPlugin,
    TestCcTest,
    DeclareHdrsVirtualPathTest,
    EffectiveTimeoutTest,
    ExportIncsListTest,
    GetCcFlagsTest,
    GetIncsListTest,
    GetenvTest,
    TestDump,
    TestExtension,
    TestGenRule,
    TestHdrDepCheck,
    TestJava,
    TestLexYacc,
    TestProtoLibrary,
    TestResourceLibrary,
    TestQuery,
    TestTestRunner,
    TestPrebuildCcLibrary,
    LinkerScriptsTest,
    BuildFromSubdirTest,
    RootCommandTest,
    TestDeprecatedDep,
    TestCcCoverage,
    TestGoCoverage,
    TestPyCoverage,
    TestSanitizerAsan,
    TestSanitizerUbsan,
    TestSanitizerTsan,
    # Newly wired in (were silently omitted from the suite):
    TestGoBinary,
    TestGoLibrary,
    TestSubdirModule,
    TestCgo,
    TestGoUnconfigured,
    TestGuardSuppression,
    TestHeaderOnlyIncstk,
    TagsTest,
]


def _main():
    """main method."""
    suite_test = unittest.TestSuite()
    suite_test.addTests(
        unittest.defaultTestLoader.loadTestsFromTestCase(tc) for tc in TEST_CASES)

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
