#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for ``BladeConfig._assign_item_value``.

Pins that a *literal* override of an item that currently holds a *deferred*
(callable / lambda) value validates against the item's underlying expected
type, not the ``_DeferredConfigValue`` wrapper. (Regression: forcing
``cc_test_config.dynamic_link=False`` under MSan failed when a project had set
it to a lambda.)
"""

import os
import sys
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import config  # noqa: E402  (sys.path tweak above)


class AssignItemValueTest(unittest.TestCase):
    def setUp(self):
        self.cfg = config.BladeConfig()

    def _deferred_bool_section(self):
        return {'dynamic_link': config._DeferredConfigValue(
            lambda blade: True, bool, 'dynamic_link')}

    def test_literal_overrides_deferred_of_same_type(self):
        section = self._deferred_bool_section()
        with mock.patch.object(self.cfg, 'error') as err:
            self.cfg._assign_item_value(section, 'dynamic_link', False)
        err.assert_not_called()
        self.assertIs(section['dynamic_link'], False)

    def test_literal_override_of_deferred_rejects_wrong_type(self):
        section = self._deferred_bool_section()
        with mock.patch.object(self.cfg, 'error') as err:
            self.cfg._assign_item_value(section, 'dynamic_link', 'not-a-bool')
        err.assert_called_once()
        # Message names the underlying expected type (bool), not the wrapper.
        self.assertIn('bool', err.call_args[0][0])

    def test_literal_override_of_literal_still_type_checked(self):
        section = {'dynamic_link': False}
        with mock.patch.object(self.cfg, 'error') as err:
            self.cfg._assign_item_value(section, 'dynamic_link', True)
        err.assert_not_called()
        self.assertIs(section['dynamic_link'], True)


if __name__ == '__main__':
    unittest.main()
