#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for blade.fatjar.

`fatjar` merges several jars into one, dropping per-jar manifests, signature
files and license/notice boilerplate, recording conflicts when two jars supply
the same path, and writing its own manifest + merge metadata. These tests
cover the exclusion predicates and drive `generate_fat_jar` end to end over
synthetic in-memory jars.
"""

import os
import sys
import tempfile
import unittest
import zipfile

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import fatjar  # noqa: E402  (sys.path tweak above)


class ExclusionPredicateTest(unittest.TestCase):
    def test_signature_files(self):
        self.assertTrue(fatjar._is_signature_file('META-INF/FOO.SF'))
        self.assertTrue(fatjar._is_signature_file('META-INF/foo.rsa'))
        self.assertTrue(fatjar._is_signature_file('META-INF/SIG-bar'))
        self.assertFalse(fatjar._is_signature_file('META-INF/services/x'))
        self.assertFalse(fatjar._is_signature_file('pkg/A.class'))

    def test_fat_jar_excluded(self):
        for name in ('META-INF/MANIFEST.MF', 'META-INF/LICENSE', 'README',
                     'NOTICE', 'META-INF/INDEX.LIST', 'META-INF/app.DSA'):
            self.assertTrue(fatjar._is_fat_jar_excluded(name), name)
        self.assertFalse(fatjar._is_fat_jar_excluded('pkg/A.class'))
        self.assertFalse(fatjar._is_fat_jar_excluded('META-INF/services/x'))


def _make_jar(path, entries):
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in entries.items():
            z.writestr(name, data)


class GenerateFatJarTest(unittest.TestCase):
    def _build(self, severity):
        d = self._dir
        jar1 = os.path.join(d, 'a.jar')
        jar2 = os.path.join(d, 'b.jar')
        _make_jar(jar1, {
            'pkg/A.class': 'A',
            'common/Shared.class': 'from-a',     # conflicts with jar2
            'META-INF/MANIFEST.MF': 'per-jar manifest',
            'META-INF/LICENSE': 'license text',
        })
        _make_jar(jar2, {
            'pkg/B.class': 'B',
            'common/Shared.class': 'from-b',     # duplicate path -> conflict
            'META-INF/app.SF': 'signature',
        })
        out = os.path.join(d, 'out.fat.jar')
        fatjar.generate_fat_jar(out, severity, '1', [jar1, jar2])
        return out

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_merge_excludes_and_metadata(self):
        out = self._build('warning')
        with zipfile.ZipFile(out, 'r') as z:
            names = set(z.namelist())
            # real classes merged from both jars
            self.assertIn('pkg/A.class', names)
            self.assertIn('pkg/B.class', names)
            # first jar wins the conflicting path
            self.assertEqual(b'from-a', z.read('common/Shared.class'))
            # per-jar boilerplate dropped
            self.assertNotIn('META-INF/LICENSE', names)
            self.assertNotIn('META-INF/app.SF', names)
            # fat jar writes its own manifest + merge metadata
            self.assertIn('Created-By: Python.Zipfile (Blade)',
                          z.read('META-INF/MANIFEST.MF').decode())
            jar_list = z.read('META-INF/blade/JAR.LIST').decode()
            self.assertIn(os.path.join(self._dir, 'a.jar'), jar_list)
            self.assertIn(os.path.join(self._dir, 'b.jar'), jar_list)
            merge_info = z.read('META-INF/blade/MERGE-INFO').decode()
            self.assertIn('[conflict]', merge_info)
            self.assertIn('common/Shared.class', merge_info)

    def test_conflict_severity_error_raises(self):
        with self.assertRaises(RuntimeError):
            self._build('error')


if __name__ == '__main__':
    unittest.main()
