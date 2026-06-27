#!/usr/bin/env python3
# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""Unit tests for MemorySanitizer's "everything must be static" handling.

MSan ships only a static runtime, so under ``--sanitizer=memory`` nothing can be
a shared library. Two pieces enforce that:

* ``main.force_static_linkage_for_msan`` overrides ``generate_dynamic`` /
  ``cc_test_config.dynamic_link`` to static -- but only when they were enabled.
* ``VcpkgLibrary.generate`` re-points an 'auto' port's dynamic label at the
  static archive when no shared lib is materialized, so the target's
  ``__outputs__`` never references a ``.so`` with no build rule.
"""

import os
import sys
import types
import unittest
from unittest import mock

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import cc_targets  # noqa: E402
from blade import config  # noqa: E402
from blade import main  # noqa: E402


class ForceStaticLinkageForMsanTest(unittest.TestCase):
    def _run(self, sanitizer_value, generate_dynamic=True, dynamic_link=True):
        options = types.SimpleNamespace(sanitizer=sanitizer_value)
        values = {'generate_dynamic': generate_dynamic, 'dynamic_link': dynamic_link}
        with mock.patch.object(config, 'get_item',
                               side_effect=lambda section, name: values[name]), \
                mock.patch.object(config, 'cc_library_config') as lib_cfg, \
                mock.patch.object(config, 'cc_test_config') as test_cfg, \
                mock.patch.object(main, 'console'):
            main.force_static_linkage_for_msan(options)
        return lib_cfg, test_cfg

    def test_msan_forces_both_static_when_enabled(self):
        lib_cfg, test_cfg = self._run('memory')
        lib_cfg.assert_called_once_with(generate_dynamic=False)
        test_cfg.assert_called_once_with(dynamic_link=False)

    def test_msan_only_overrides_enabled_options(self):
        # generate_dynamic already off, dynamic_link still on -> override only
        # the one that was enabled (no needless override / notice for the other).
        lib_cfg, test_cfg = self._run('memory', generate_dynamic=False)
        lib_cfg.assert_not_called()
        test_cfg.assert_called_once_with(dynamic_link=False)

    def test_msan_skips_when_already_static(self):
        lib_cfg, test_cfg = self._run('memory', generate_dynamic=False, dynamic_link=False)
        lib_cfg.assert_not_called()
        test_cfg.assert_not_called()

    def test_other_sanitizer_is_noop(self):
        lib_cfg, test_cfg = self._run('address')
        lib_cfg.assert_not_called()
        test_cfg.assert_not_called()

    def test_no_sanitizer_is_noop(self):
        lib_cfg, test_cfg = self._run(None)
        lib_cfg.assert_not_called()
        test_cfg.assert_not_called()


def _vcpkg_auto_lib(wants_dynamic):
    lib = cc_targets.VcpkgLibrary.__new__(cc_targets.VcpkgLibrary)
    lib.attr = {
        'static_source': '/vcpkg/lib/libfoo.a',
        'dynamic_source': '/vcpkg/lib-shared/libfoo.so',
        'dynamic_target': '/build/libfoo.so',
    }
    lib.build_dir = '/build'
    lib.blade = mock.Mock()
    lib.blade.get_build_toolchain.return_value = mock.Mock(DYNAMIC_LIB_LABEL='so')
    lib._vcpkg_wants_dynamic = mock.Mock(return_value=wants_dynamic)
    lib._emit_archive_syms = mock.Mock()
    lib.generate_build = mock.Mock()
    lib._add_target_file = mock.Mock()
    return lib


class VcpkgAutoPortStaticRepointTest(unittest.TestCase):
    def test_static_only_repoints_dynamic_label_to_archive(self):
        # No dynamic-link consumer -> no .so built; the DYNAMIC label must be
        # re-pointed to the static .a so __outputs__ has no ruleless .so.
        lib = _vcpkg_auto_lib(wants_dynamic=False)
        cc_targets.VcpkgLibrary.generate(lib)
        lib.generate_build.assert_not_called()
        lib._add_target_file.assert_called_once_with('so', '/vcpkg/lib/libfoo.a')

    def test_dynamic_wanted_copies_so_and_keeps_label(self):
        lib = _vcpkg_auto_lib(wants_dynamic=True)
        cc_targets.VcpkgLibrary.generate(lib)
        lib.generate_build.assert_called_once()  # the .so copy rule
        lib._add_target_file.assert_not_called()  # label not re-pointed


if __name__ == '__main__':
    unittest.main()
