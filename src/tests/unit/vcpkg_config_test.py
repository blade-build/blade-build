#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.
#
# Unit tests for the vcpkg_config BLADE_ROOT rule (issue #1236).

"""Tests the vcpkg_config surface added as PR1 of native vcpkg support.

This PR only adds the config rule; nothing consumes it yet. Covered here:

  * Template defaults so the documented contract stays pinned.
  * `vcpkg_config()` accepts the two `packages` value shapes (a bare version
    string, or a dict with version/features) and rejects malformed specs at
    config-load time.
  * Values round-trip through `config.get_section('vcpkg_config')`.
"""

import os
import sys
import unittest
import unittest.mock as mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402


class VcpkgConfigDefaultsTest(unittest.TestCase):
    """Pin the template defaults; vcpkg's manifest model is one version /
    feature-set per package per workspace, so this is a single section."""

    def setUp(self):
        self._template = config._CONFIG_TEMPLATE['vcpkg_config']

    def test_baseline_defaults_empty(self):
        # Empty = unpinned (Tier 0); a later phase warns. Defaulting to a
        # value would silently pin everyone to an arbitrary ports tree.
        self.assertEqual(self._template['baseline'], '')

    def test_packages_defaults_empty_dict(self):
        self.assertEqual(self._template['packages'], {})

    def test_registries_defaults_empty_list(self):
        self.assertEqual(self._template['registries'], [])

    def test_root_defaults_empty(self):
        # Empty = use $VCPKG_ROOT.
        self.assertEqual(self._template['root'], '')

    def test_triplet_defaults_auto(self):
        self.assertEqual(self._template['triplet'], 'auto')

    def test_install_dir_default(self):
        self.assertEqual(self._template['install_dir'], '.cache/vcpkg')

    def test_binary_cache_defaults_auto(self):
        self.assertEqual(self._template['binary_cache'], 'auto')

    def test_direct_use_allowed_defaults_empty(self):
        # Empty = anywhere (governance enforcement is a later phase).
        self.assertEqual(self._template['direct_use_allowed'], [])

    def test_help_text_present(self):
        """`blade dump --config` needs the section help string."""
        self.assertIn('__help__', self._template)


class VcpkgConfigValidationTest(unittest.TestCase):
    """`packages` accepts str or {version, features}; anything else errors."""

    def setUp(self):
        self._bc = config._blade_config
        self._saved = dict(self._bc.config)

    def tearDown(self):
        self._bc.config = self._saved

    def _call(self, **kwargs):
        warnings, errors = [], []
        with mock.patch.object(self._bc, 'warning', side_effect=warnings.append), \
             mock.patch.object(self._bc, 'error', side_effect=errors.append):
            config.vcpkg_config(**kwargs)
        return warnings, errors

    def test_string_version_accepted(self):
        _, errors = self._call(packages={'fmt': '10.2.1'})
        self.assertEqual(errors, [])

    def test_dict_spec_accepted(self):
        _, errors = self._call(
            packages={'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']}})
        self.assertEqual(errors, [])

    def test_dict_version_only_accepted(self):
        _, errors = self._call(packages={'openssl': {'version': '3.2.1'}})
        self.assertEqual(errors, [])

    def test_unknown_spec_key_errors(self):
        """A typo'd key (e.g. `versions`) must surface at config-load time
        rather than silently dropping the intended version pin."""
        _, errors = self._call(packages={'fmt': {'versions': '10.2.1'}})
        self.assertEqual(len(errors), 1)
        self.assertIn('fmt', errors[0])

    def test_features_must_be_list(self):
        _, errors = self._call(
            packages={'curl': {'version': '8.5.0', 'features': 'ssl'}})
        self.assertEqual(len(errors), 1)
        self.assertIn('features', errors[0])

    def test_scalar_spec_errors(self):
        """`'fmt': 10` (a bare int) is neither a version string nor a spec."""
        _, errors = self._call(packages={'fmt': 10})
        self.assertEqual(len(errors), 1)
        self.assertIn('fmt', errors[0])

    def test_packages_must_be_dict(self):
        """A list instead of a dict triggers at least the config type check."""
        _, errors = self._call(packages=['fmt'])
        self.assertGreaterEqual(len(errors), 1)


class VcpkgConfigReadbackTest(unittest.TestCase):
    """Values set by the rule round-trip through get_section."""

    def setUp(self):
        self._bc = config._blade_config
        self._saved = dict(self._bc.config)

    def tearDown(self):
        self._bc.config = self._saved

    def test_fields_round_trip(self):
        with mock.patch.object(self._bc, 'warning'), \
             mock.patch.object(self._bc, 'error'):
            config.vcpkg_config(
                baseline='2024-12-15',
                packages={'fmt': '10.2.1'},
                triplet='auto',
            )
        section = config.get_section('vcpkg_config')
        self.assertEqual(section['baseline'], '2024-12-15')
        self.assertEqual(section['packages'], {'fmt': '10.2.1'})
        # Untouched fields keep their template defaults.
        self.assertEqual(section['install_dir'], '.cache/vcpkg')


if __name__ == '__main__':
    unittest.main()
