#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.blade_types.

"""Smoke tests for the shared type aliases module.

There's no runtime logic to exercise -- ``StrOrList`` and ``StrOrListOpt``
are type aliases -- but we still want a cheap CI signal that:

1. The module imports cleanly on the supported Python versions (3.10+),
2. The aliases are actually exported (so a typo in ``__all__`` or a future
   rename cannot slip through unnoticed),
3. The module name stays ``blade_types`` (never ``types``), so we don't
   accidentally reintroduce a stdlib-shadow pitfall.
"""

import os
import sys
import unittest

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import blade_types  # noqa: E402


class BladeTypesTest(unittest.TestCase):

    def test_module_name_is_not_types(self):
        # Guard against anyone renaming blade_types back to plain ``types``,
        # which would shadow the stdlib module in a confusing way.
        self.assertEqual(blade_types.__name__, 'blade.blade_types')

    def test_str_or_list_exported(self):
        self.assertTrue(hasattr(blade_types, 'StrOrList'))
        self.assertIn('StrOrList', blade_types.__all__)

    def test_str_or_list_opt_exported(self):
        self.assertTrue(hasattr(blade_types, 'StrOrListOpt'))
        self.assertIn('StrOrListOpt', blade_types.__all__)


if __name__ == '__main__':
    unittest.main()
