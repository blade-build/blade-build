#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.java_targets.JavaTest._apply_junit_libs_from_config.

"""Unit tests for JavaTest's `java_test_config.junit_libs` auto-injection.

The hook turns the ``java_test_config(junit_libs=[...])`` config key
from an inert schema entry into a real implicit-deps injection point,
so every ``java_test`` target in a workspace automatically pulls its
JUnit runtime out of the workspace-level config instead of repeating
`//thirdparty/junit:junit` in every BUILD file.

What we pin here:

* When ``junit_libs`` is non-empty, every label is forwarded to
  ``Target._add_implicit_library`` in order.
* When ``junit_libs`` is empty (the default, or an explicit ``[]``),
  the target emits a single warning pointing at the config key and
  calls ``_add_implicit_library`` zero times — so workspaces that
  prefer per-target explicit `deps` keep working.
* We do *not* construct a real ``JavaTest`` (that would need the
  full build manager / workspace). Instead we
  ``JavaTest.__new__(JavaTest)`` a bare instance and stub the two
  collaborators the method touches: ``config.get_item`` and
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

from blade import java_targets  # noqa: E402  (sys.path tweak above)


def _bare_java_test():
    """Build a ``JavaTest`` instance bypassing ``__init__``.

    The hook under test reads nothing from ``self`` other than the
    two methods we stub below, so we skip the expensive constructor
    chain that would otherwise require a live build manager / loaded
    BUILD file / workspace root.
    """
    return java_targets.JavaTest.__new__(java_targets.JavaTest)


class ApplyJunitLibsFromConfigTest(unittest.TestCase):
    """Cover every branch of JavaTest._apply_junit_libs_from_config."""

    def test_configured_libs_are_forwarded_to_add_implicit_library(self):
        """The happy path: `java_test_config.junit_libs` lists one or
        more labels and the hook forwards the *list* (not one call per
        label) to ``_add_implicit_library``.

        Forwarding the list as a whole — matching scala_targets and
        proto_library_target — keeps ordering deterministic and
        delegates the per-label unification (''//'' prefixing, ``#``
        system-lib handling, dedup against ``self.deps``) to the
        existing ``Target._add_implicit_library`` helper.
        """
        target = _bare_java_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        configured = ['//thirdparty/junit:junit', '//thirdparty/hamcrest:core']
        with mock.patch.object(java_targets.config, 'get_item', return_value=configured):
            target._apply_junit_libs_from_config()

        target._add_implicit_library.assert_called_once_with(configured)
        target.warning.assert_not_called()

    def test_empty_list_warns_and_does_not_inject(self):
        """The documented default: an empty list means "no auto-
        injection", and users must list JUnit in ``deps`` explicitly.

        In that case the hook must *not* touch ``_add_implicit_library``
        (otherwise we'd inject a bogus empty label set and hide the
        missing-config from users), and it must emit exactly one
        warning pointing at the config key so blade -v shows something
        actionable."""
        target = _bare_java_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        with mock.patch.object(java_targets.config, 'get_item', return_value=[]):
            target._apply_junit_libs_from_config()

        target._add_implicit_library.assert_not_called()
        target.warning.assert_called_once()
        (warn_msg,), _ = target.warning.call_args
        self.assertIn('java_test_config.junit_libs', warn_msg)

    def test_none_is_treated_the_same_as_empty(self):
        """``config.get_item`` returns ``None`` rather than ``[]`` when
        a user deletes the key entirely from their ``BLADE_ROOT``.

        Both shapes mean "not configured" and must take the same
        branch — no injection, one warning. Locks in this equivalence
        so a future refactor doesn't regress one case while preserving
        the other."""
        target = _bare_java_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        with mock.patch.object(java_targets.config, 'get_item', return_value=None):
            target._apply_junit_libs_from_config()

        target._add_implicit_library.assert_not_called()
        target.warning.assert_called_once()

    def test_looks_up_the_documented_config_path(self):
        """Regression pin: the hook must read from
        ``('java_test_config', 'junit_libs')`` exactly. If somebody
        later refactors the schema and forgets to update this call
        site, the hook would silently read ``None`` from a mistyped
        key and fall through to the warning branch — hiding the bug.
        This test fails fast on that drift."""
        target = _bare_java_test()
        target._add_implicit_library = mock.Mock()
        target.warning = mock.Mock()

        with mock.patch.object(java_targets.config, 'get_item',
                               return_value=['//x:y']) as get_item:
            target._apply_junit_libs_from_config()

        get_item.assert_called_once_with('java_test_config', 'junit_libs')


class SchemaTest(unittest.TestCase):
    """Pin the config schema so the hook has something to read."""

    def test_junit_libs_key_exists_with_empty_default(self):
        """The key must be declared in ``config.py`` with a list
        default. If this ever regresses, every workspace would start
        seeing an AttributeError / KeyError instead of the documented
        "not configured" warning."""
        from blade import config as config_mod
        # Force the module to populate its default schema by reading
        # a key we know exists.
        default = config_mod.get_item('java_test_config', 'junit_libs')
        # The default in schema is []; after a real config load it may
        # be any list. We only check the shape.
        self.assertIsInstance(default, list)


if __name__ == '__main__':
    unittest.main()
