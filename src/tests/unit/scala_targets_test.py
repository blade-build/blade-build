#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.scala_targets.ScalaTest._apply_scalatest_libs_from_config.

"""Unit tests for ScalaTest's `scala_test_config.scalatest_libs` auto-injection.

The hook is the scala-side twin of
``JavaTest._apply_junit_libs_from_config``: it turns the
``scala_test_config(scalatest_libs=[...])`` config key into a real
implicit-deps injection point, so every ``scala_test`` target in a
workspace automatically pulls its ScalaTest runtime out of the
workspace-level config instead of repeating the dep by hand in
every BUILD file.

What we pin here (must stay in lock-step with
``java_targets_test.ApplyJunitLibsFromConfigTest``):

* When ``scalatest_libs`` is non-empty, the full list is forwarded
  to ``Target._add_implicit_library`` in one call — delegating
  per-label unification/dedup to that existing helper.
* When ``scalatest_libs`` is empty (``[]``) or missing (``None``),
  no implicit library is added and exactly one target-attributed
  warning is emitted, pointing at the config key so ``blade -v``
  shows something actionable.
* The hook must query ``config.get_item`` with the exact pair
  ``('scala_test_config', 'scalatest_libs')`` — a regression pin
  against future schema-key drift.

We do *not* construct a real ``ScalaTest`` (that would need the
full build manager / a loaded BUILD file / a workspace root).
Instead we ``ScalaTest.__new__(ScalaTest)`` a bare instance and
stub the two collaborators the method touches: the module-level
``config.get_item`` and the instance-level
``self._add_implicit_library`` / ``self.warning``. This keeps the
test sharply focused on the injection contract.
"""

import os
import sys
import unittest
from unittest import mock

# Make ``import blade.*`` resolve against the in-tree sources without
# requiring blade to be installed.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import scala_targets  # noqa: E402  (sys.path tweak above)


def _bare_scala_test():
    """Build a ``ScalaTest`` instance bypassing ``__init__``.

    The hook under test reads nothing from ``self`` other than the
    two methods we stub below, so we skip the expensive constructor
    chain that would otherwise require a live build manager / loaded
    BUILD file / workspace root.
    """
    return scala_targets.ScalaTest.__new__(scala_targets.ScalaTest)


class ApplyScalatestLibsFromConfigTest(unittest.TestCase):
    """Cover every branch of ScalaTest._apply_scalatest_libs_from_config."""

    def test_configured_libs_are_forwarded_to_add_implicit_library(self):
        """Happy path: the config lists one or more labels, and the
        hook forwards the *list* (not one call per label) to
        ``_add_implicit_library``. Matching the java/proto shape keeps
        ordering deterministic and lets ``Target._add_implicit_library``
        do the per-label unification / dedup against ``self.deps``.
        """
        target = _bare_scala_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        configured = ['//thirdparty/scalatest:scalatest', '//thirdparty/scalactic:scalactic']
        with mock.patch.object(scala_targets.config, 'get_item', return_value=configured):
            target._apply_scalatest_libs_from_config()

        target._add_implicit_library.assert_called_once_with(configured)
        target.warning.assert_not_called()

    def test_empty_list_warns_and_does_not_inject(self):
        """Documented default: an empty list means "no auto-injection",
        users must list ScalaTest in ``deps`` explicitly.

        The hook must *not* touch ``_add_implicit_library`` (otherwise
        we'd inject a bogus empty label set and hide the missing
        config from users), and it must emit exactly one
        target-attributed warning mentioning the config key."""
        target = _bare_scala_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        with mock.patch.object(scala_targets.config, 'get_item', return_value=[]):
            target._apply_scalatest_libs_from_config()

        target._add_implicit_library.assert_not_called()
        target.warning.assert_called_once()
        (warn_msg,), _ = target.warning.call_args
        self.assertIn('scala_test_config.scalatest_libs', warn_msg)

    def test_none_is_treated_the_same_as_empty(self):
        """``config.get_item`` returns ``None`` rather than ``[]`` when
        a user deletes the key entirely from their ``BLADE_ROOT``.

        Both shapes mean "not configured" and must take the same
        branch — no injection, one warning. Locks in this equivalence
        so a future refactor doesn't regress one case while preserving
        the other."""
        target = _bare_scala_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        with mock.patch.object(scala_targets.config, 'get_item', return_value=None):
            target._apply_scalatest_libs_from_config()

        target._add_implicit_library.assert_not_called()
        target.warning.assert_called_once()

    def test_looks_up_the_documented_config_path(self):
        """Regression pin: the hook must read from
        ``('scala_test_config', 'scalatest_libs')`` exactly. If
        somebody later refactors the schema and forgets to update
        this call site, the hook would silently read ``None`` from a
        mistyped key and fall through to the warning branch — hiding
        the bug. This test fails fast on that drift."""
        target = _bare_scala_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        with mock.patch.object(scala_targets.config, 'get_item',
                               return_value=['//x:y']) as get_item:
            target._apply_scalatest_libs_from_config()

        get_item.assert_called_once_with('scala_test_config', 'scalatest_libs')


class SchemaTest(unittest.TestCase):
    """Pin the config schema so the hook has something to read."""

    def test_scalatest_libs_key_exists_with_empty_default(self):
        """The key must be declared in ``config.py`` with a list
        default. If this ever regresses, every workspace would start
        seeing an AttributeError / KeyError instead of the documented
        "not configured" warning."""
        from blade import config as config_mod
        default = config_mod.get_item('scala_test_config', 'scalatest_libs')
        # Default in schema is []; after a real config load it may be
        # any list. Only the shape is part of the contract.
        self.assertIsInstance(default, list)


if __name__ == '__main__':
    unittest.main()
