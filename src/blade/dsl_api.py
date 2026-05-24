# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>
# Date:   2021-03-04

# This file creates safe API modules by dynamically injecting attributes
# onto types.ModuleType instances (_safe_blade_module, _safe_workspace_module).
# pyright can't statically track these — suppress file-wide.
# pyright: reportAttributeAccessIssue=false

"""
API for BUILD files and extensions.
"""

import os
import re
import types

import blade

from blade import config
from blade import console
from blade import util
from blade import workspace


def _new_module(name):
    """Make an new empty module."""
    # return imp.new_module(name)
    return types.ModuleType(name)


def _copy_module_members(to_mod, from_mod, names):
    """Copy specified attrs from one module to another."""
    for name in names:
        setattr(to_mod, name, getattr(from_mod, name))


def _safe_config_module():
    """Make the safe blade.config module."""
    module = _new_module('config')
    _copy_module_members(module, config, [
        'get_item',
        'get_section',
    ])
    return module


def _safe_console_module():
    """Make the safe blade.console module."""
    module = _new_module('console')
    def make_wrapper(severity):
        def wrapper(message):
            console.diagnose(util.calling_source_location(1), severity, message)
        return wrapper
    for severity in ['debug', 'info', 'notice', 'warning', 'error']:
        setattr(module, severity, make_wrapper(severity))
    return module


def _safe_path_module():
    """Make the safe blade.console module."""
    module = _new_module('path')
    _copy_module_members(module, os.path, [
        'abspath',
        'basename',
        'dirname',
        'exists',
        'join',
        'relpath',
        'normpath',
        'sep',
        'splitext',
    ])
    return module


def _safe_util_module():
    """Make the safe blade.util module."""
    module = _new_module('util')
    _copy_module_members(module, util, [
        'regular_variable_name',
        'var_to_list',
    ])
    return module


def _safe_workspace_module():
    """Make the safe blade.workspace module."""
    module = _new_module('workspace')
    module.root_dir = workspace.current().root_dir
    module.build_dir = workspace.current().build_dir
    return module


class _CCToolchainProxy:
    """Read-only toolchain proxy exposed as ``blade.cc_toolchain`` in BUILD files.

    Only properties relevant to BUILD-level decisions (file naming, platform
    detection) are surfaced.  Command lines and internal path lists are
    deliberately excluded.
    """

    # Accessed lazily to avoid ordering issues at module-import time.
    @property
    def _tc(self):
        return blade.build_manager.instance.get_build_toolchain()

    # -- file naming ------------------------------------------------

    @property
    def obj_suffix(self) -> str:
        return self._tc.obj_suffix

    @property
    def static_lib_suffix(self) -> str:
        return self._tc.static_lib_suffix

    @property
    def dynamic_lib_suffix(self) -> str:
        return self._tc.dynamic_lib_suffix

    @property
    def lib_prefix(self) -> str:
        return self._tc.lib_prefix

    @property
    def all_dynamic_lib_suffixes(self) -> tuple[str, ...]:
        return self._tc.all_dynamic_lib_suffixes

    # -- capability queries -----------------------------------------

    def supports_resource_compilation(self) -> bool:
        return self._tc.supports_resource_compilation()

    def cc_is(self, vendor: str) -> bool:
        return self._tc.cc_is(vendor)

    # -- output name helpers ----------------------------------------

    def object_file_of(self, src: str) -> str:
        return self._tc.object_file_of(src)

    def static_library_name(self, name: str) -> str:
        return self._tc.static_library_name(name)

    def dynamic_library_name(self, name: str) -> str:
        return self._tc.dynamic_library_name(name)

    def executable_file_name(self, name: str) -> str:
        return self._tc.executable_file_name(name)


def _safe_blade_module():
    """Make the safe blade module."""
    module = _new_module('blade')
    module.config = _safe_config_module()
    module.console = _safe_console_module()
    module.current_source_dir = blade.current_source_dir
    module.current_target_dir = blade.current_target_dir
    module.environ = os.environ
    module.path = _safe_path_module()
    module.re = re
    module.util = _safe_util_module()
    module.workspace = _safe_workspace_module()
    module.cc_toolchain = _CCToolchainProxy()
    return module


__blade = None


def get_blade_module():
    """Get or create the `blade` API module."""
    global __blade
    if not __blade:
        __blade = _safe_blade_module()
    return __blade
