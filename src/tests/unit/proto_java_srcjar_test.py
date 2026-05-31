#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for the proto -> Java srcjar plumbing (issue #1054).

`generate_proto_java_srcjar` runs protoc (here a stand-in that just writes
`.java` files) and zips whatever it produced into a `.srcjar` -- so an
unpredictable output set (e.g. `option java_multiple_files = true;`) is handled
without predicting filenames. `_expand_java_srcjars` is the inverse on the
javac side: it turns a `.srcjar` input back into its `.java` files.
"""

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import builtin_tools  # noqa: E402  (sys.path tweak above)

# A stand-in for protoc: writes N .java files (in a package subdir) into the
# gen dir passed as argv[1]. Lets us exercise the wrapper without a real protoc.
_FAKE_PROTOC = (
    'import os,sys; g=sys.argv[1]; d=os.path.join(g,"mypkg"); os.makedirs(d,exist_ok=True);'
    '[open(os.path.join(d,n),"w").write("//"+n) for n in ("A.java","B.java","C.java")]'
)


class GenerateProtoJavaSrcjarTest(unittest.TestCase):
    def test_zips_all_generated_java_with_forward_slashes(self):
        with tempfile.TemporaryDirectory() as d:
            srcjar = os.path.join(d, 'out.srcjar')
            gendir = os.path.join(d, 'gen')
            cmd = [sys.executable, '-c', _FAKE_PROTOC, gendir]
            builtin_tools.generate_proto_java_srcjar([srcjar, gendir, '--'] + cmd)
            self.assertTrue(os.path.exists(srcjar))
            with zipfile.ZipFile(srcjar) as z:
                names = set(z.namelist())
            # All three "messages" captured -- the multiple-files case -- with
            # POSIX separators (valid jar entries).
            self.assertEqual({'mypkg/A.java', 'mypkg/B.java', 'mypkg/C.java'}, names)

    def test_stale_gendir_is_cleared(self):
        with tempfile.TemporaryDirectory() as d:
            srcjar = os.path.join(d, 'out.srcjar')
            gendir = os.path.join(d, 'gen')
            os.makedirs(gendir)
            open(os.path.join(gendir, 'Stale.java'), 'w').close()  # leftover
            cmd = [sys.executable, '-c', _FAKE_PROTOC, gendir]
            builtin_tools.generate_proto_java_srcjar([srcjar, gendir, '--'] + cmd)
            with zipfile.ZipFile(srcjar) as z:
                names = set(z.namelist())
            self.assertNotIn('Stale.java', names)  # cleared before protoc


_MULTI_PROTO = '''\
syntax = "proto3";
package e2e;
option java_package = "e2e.gen";
option java_multiple_files = true;
message Alpha { string a = 1; }
message Beta { int32 b = 1; }
enum Color { RED = 0; GREEN = 1; }
'''

_SINGLE_PROTO = '''\
syntax = "proto3";
package e2e;
option java_package = "e2e.gen";
message Solo { string s = 1; }
'''


@unittest.skipUnless(shutil.which('protoc'), 'protoc not on PATH')
class RealProtocSrcjarTest(unittest.TestCase):
    """End-to-end with the real protoc: the srcjar must capture protoc's actual
    output, however many files it is -- in particular the java_multiple_files
    case (one .java per top-level type), which the old single-file prediction
    could not handle. See #1054."""

    def _srcjar_entries(self, proto_text, name):
        with tempfile.TemporaryDirectory() as d:
            proto = os.path.join(d, name + '.proto')
            with open(proto, 'w') as f:
                f.write(proto_text)
            srcjar = os.path.join(d, name + '.srcjar')
            gendir = os.path.join(d, name + '.javagen')
            cmd = ['protoc', '--proto_path=' + d, '--java_out=' + gendir, proto]
            builtin_tools.generate_proto_java_srcjar([srcjar, gendir, '--'] + cmd)
            with zipfile.ZipFile(srcjar) as z:
                return set(z.namelist())

    def test_java_multiple_files_yields_one_file_per_type(self):
        entries = self._srcjar_entries(_MULTI_PROTO, 'multi')
        # protoc emits a separate .java per top-level message/enum (+OrBuilder).
        self.assertIn('e2e/gen/Alpha.java', entries)
        self.assertIn('e2e/gen/Beta.java', entries)
        self.assertIn('e2e/gen/Color.java', entries)
        self.assertGreaterEqual(len(entries), 3)

    def test_single_file_layout_yields_one_outer_class(self):
        entries = self._srcjar_entries(_SINGLE_PROTO, 'single')
        # Default layout: one outer class containing the nested type.
        self.assertEqual(1, len(entries))
        self.assertTrue(next(iter(entries)).endswith('.java'))


class ExpandJavaSrcjarsTest(unittest.TestCase):
    def test_srcjar_input_expands_to_extracted_java(self):
        with tempfile.TemporaryDirectory() as d:
            srcjar = os.path.join(d, 'in.srcjar')
            with zipfile.ZipFile(srcjar, 'w') as z:
                z.writestr('p/A.java', '//a')
                z.writestr('p/B.java', '//b')
                z.writestr('p/notes.txt', 'ignored')
            out = builtin_tools._expand_java_srcjars([srcjar], os.path.join(d, 'x'))
            self.assertEqual(2, len(out))
            self.assertTrue(all(s.endswith('.java') and os.path.isfile(s) for s in out))

    def test_plain_sources_pass_through_untouched(self):
        srcs = ['a/Foo.java', 'b/Bar.java']
        self.assertEqual(srcs, builtin_tools._expand_java_srcjars(srcs, '/unused'))


if __name__ == '__main__':
    unittest.main()
