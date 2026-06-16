# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# This is the test module for proto_library target.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   October 20, 2011


import sys
import blade_test


class TestProtoLibrary(blade_test.TargetTest):
    """Test proto_library."""
    def setUp(self):
        """setup method."""
        self.doSetUp('proto')

    def testGenerateRules(self):
        """Test that rules are generated correctly."""
        self.assertTrue(self.dryRun('build', '--generate-java'))

        com_uses_line = self.findCommand(['use_protos.cpp.o', '-c'])
        com_proto_cpp_option = self.findCommand(['protobuf/bin/protoc', 'cpp_out', 'rpc_option.proto'])
        com_proto_cpp_meta = self.findCommand(['protobuf/bin/protoc', 'cpp_out', 'rpc_meta_info.proto'])
        com_proto_java_option = self.findCommand(['protobuf/bin/protoc', 'java_out', 'rpc_option.proto'])
        com_proto_java_meta = self.findCommand(['protobuf/bin/protoc', 'java_out', 'rpc_meta_info.proto'])

        com_proto_option_cc = self.findCommand(['rpc_option.pb.cc.o', '-c'])
        com_proto_meta_cc = self.findCommand(['rpc_meta_info.pb.cc.o', '-c'])
        meta_depends_libs = self.findCommand(['-shared', 'librpc_meta_info_proto.so'])
        uses_depends_libs = self.findCommand(['-shared', 'libuse_protos.so'])

        self.assertCxxFlags(com_uses_line)

        self.assertTrue(com_proto_cpp_option)
        self.assertTrue(com_proto_cpp_meta)
        self.assertTrue(com_proto_java_option)
        self.assertTrue(com_proto_java_meta)

        self.assertNoWarningCxxFlags(com_proto_option_cc)
        self.assertNoWarningCxxFlags(com_proto_meta_cc)

        self.assertTrue(meta_depends_libs)
        self.assertIn('libuse_protos.so', uses_depends_libs)

    def testCrossRootImportProtoPath(self):
        """A proto_library whose dependency is rooted under a different
        strip_import_prefix compiles with that dependency's import root added as
        a `-I` proto-path, so a cross-root import resolves."""
        self.assertTrue(self.dryRun())
        # cross_root_proto is rooted at proto/main_root; its dep other_root_proto
        # is rooted at proto/sub -> that root must appear as a -I on the compile.
        cmd = self.findCommand(['--proto_path=proto/main_root', '--cpp_out'])
        self.assertIn('-I=proto/sub', cmd)


if __name__ == '__main__':
    blade_test.run(TestProtoLibrary)
