#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for well-known-proto auto-discovery (issue #1339).

`proto_library_target.well_known_protos` whitelists the .proto files protobuf
itself ships (google/protobuf/*.proto) for protoc's --direct_dependencies. An
explicit `proto_library_config.well_known_protos` wins; otherwise it discovers
them from the protobuf include tree so the list need not be hand-maintained.
"""

import os
import sys
import tempfile
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import proto_library_target as plt  # noqa: E402


class WellKnownProtosTest(unittest.TestCase):
    def setUp(self):
        plt._well_known_protos_cache.clear()

    def _cfg(self, **over):
        c = {'protoc': 'protoc', 'protobuf_incs': [], 'well_known_protos': []}
        c.update(over)
        return c

    def test_explicit_list_wins(self):
        # A configured list is used verbatim, no discovery.
        cfg = self._cfg(well_known_protos=['google/protobuf/any.proto'],
                        protobuf_incs=['/nonexistent'])
        self.assertEqual(plt.well_known_protos(None, 'b', cfg),
                         ['google/protobuf/any.proto'])

    def test_discovers_from_protobuf_incs(self):
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, 'google', 'protobuf')
            os.makedirs(os.path.join(base, 'compiler'))
            for n in ('any.proto', 'timestamp.proto'):
                open(os.path.join(base, n), 'w').close()
            open(os.path.join(base, 'compiler', 'plugin.proto'), 'w').close()
            open(os.path.join(base, 'README.txt'), 'w').close()  # not a .proto
            got = plt.well_known_protos(None, 'b', self._cfg(protobuf_incs=[d]))
            self.assertEqual(got, [
                'google/protobuf/any.proto',
                'google/protobuf/compiler/plugin.proto',
                'google/protobuf/timestamp.proto',
            ])

    def test_no_include_falls_back_to_default(self):
        # No resolvable include tree -> the built-in safety net, not [].
        self.assertEqual(plt.well_known_protos(None, 'b', self._cfg()),
                         list(plt._DEFAULT_WELL_KNOWN_PROTOS))

    def test_missing_google_protobuf_dir_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as d:  # exists but no google/protobuf/
            self.assertEqual(
                plt.well_known_protos(None, 'b', self._cfg(protobuf_incs=[d])),
                list(plt._DEFAULT_WELL_KNOWN_PROTOS))

    def test_default_fallback_matches_discovery_for_a_modern_protobuf(self):
        # The hand-maintained safety net should equal what discovery finds for a
        # typical protobuf layout, so a fallback build behaves like a normal one.
        with tempfile.TemporaryDirectory() as d:
            base = os.path.join(d, 'google', 'protobuf')
            os.makedirs(os.path.join(base, 'compiler'))
            names = [p.split('google/protobuf/')[1]
                     for p in plt._DEFAULT_WELL_KNOWN_PROTOS]
            for n in names:
                full = os.path.join(base, *n.split('/'))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                open(full, 'w').close()
            self.assertEqual(plt.well_known_protos(None, 'b', self._cfg(protobuf_incs=[d])),
                             list(plt._DEFAULT_WELL_KNOWN_PROTOS))


if __name__ == '__main__':
    unittest.main()
