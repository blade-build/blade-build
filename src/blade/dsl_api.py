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
import sys
import types

import blade

from blade import build_attributes
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
    ws = workspace.current()
    assert ws is not None, 'workspace must be initialized before accessing blade.workspace'
    module.root_dir = ws.root_dir
    module.build_dir = ws.build_dir
    return module


def _host_os():
    """Host OS name: ``'darwin'``, ``'linux'``, or ``'windows'``."""
    if sys.platform == 'win32':
        return 'windows'
    return sys.platform


def _host_arch():
    """Canonical host CPU architecture: ``'x86_64'``, ``'aarch64'``, etc."""
    import platform
    machine = platform.machine()
    if machine.lower() in ('arm64', 'aarch64'):
        return 'aarch64'
    if machine.lower() in ('amd64', 'x86_64'):
        return 'x86_64'
    return machine.lower()


class _CCToolchainProxy:
    """Read-only toolchain proxy exposed as ``blade.cc_toolchain`` in BUILD files.

    File-naming properties, tool lookup, and target platform / architecture
    info (useful for cross-compilation-aware deps in BUILD files).
    """

    @property
    def _tc(self):
        return blade.build_manager.instance.get_build_toolchain()

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
    def exe_suffix(self) -> str:
        return self._tc.exe_suffix

    @property
    def cc_vendor(self) -> str:
        """Compiler vendor: ``'gcc'``, ``'clang'``, or ``'unknown'``."""
        return self._tc._cc_vendor

    @property
    def target_os(self) -> str:
        """Target OS: ``'darwin'``, ``'linux'``, ``'windows'``."""
        return self._tc.target_os

    @property
    def target_arch(self) -> str:
        """Target CPU architecture: ``'x86_64'``, ``'aarch64'``, etc."""
        return self._tc.target_arch

    def tool(self, key: str) -> str | None:
        """Return tool path for *key*, or ``None`` if not available.

        Supported keys: ``'cc'``, ``'cxx'``, ``'ld'``, ``'ar'``, ``'rc'``, ``'as'``.
        """
        return self._tc.tool(key)


# Attributes only available during BUILD phase (not when loading BLADE_ROOT).
_BUILD_ONLY_ATTRS = frozenset({
    'cc_toolchain',
    'config',
    'current_source_dir',
    'current_target_dir',
    'workspace',
})

_BUILD_ONLY_HINT = (
    ' is only available during BUILD phase. '
    'Use a function-valued config item: lambda blade: blade.'
)


class _BladeModule(types.ModuleType):
    """Blade module with read-only properties and config-phase guards."""

    def __init__(self, name: str, config_phase: bool = False):
        super().__init__(name)
        self._config_phase = config_phase

    def __getattr__(self, name: str):
        if self._config_phase and name in _BUILD_ONLY_ATTRS:
            console.fatal(f'blade.{name}{_BUILD_ONLY_HINT}{name}')
        raise AttributeError(f"module 'blade' has no attribute {name!r}")

    @property
    def build_type(self) -> str:
        """Current build type: ``'debug'`` or ``'release'``."""
        instance = blade.build_manager.instance
        if instance is not None:
            return instance.get_options().profile
        return 'debug' if build_attributes.attributes.is_debug() else 'release'

    def build_type_is_debug(self) -> bool:
        """Return ``True`` if the build type is ``'debug'``."""
        return self.build_type == 'debug'


def _safe_blade_module(config_phase: bool = True):
    """Make the safe blade module."""
    module = _BladeModule('blade', config_phase=config_phase)
    module.console = _safe_console_module()
    module.path = _safe_path_module()
    module.re = re
    module.util = _safe_util_module()
    module.host_os = _host_os()
    module.host_arch = _host_arch()
    return module


__blade = None


def get_blade_module():
    """Get or create the `blade` API module."""
    global __blade
    if not __blade:
        __blade = _safe_blade_module(config_phase=False)
        # These attributes only exists since the load pharse.
        __blade.config = _safe_config_module()
        __blade.current_source_dir = blade.current_source_dir
        __blade.current_target_dir = blade.current_target_dir
        __blade.cc_toolchain = _CCToolchainProxy()
        __blade.workspace = _safe_workspace_module()

    return __blade


def new_blade_module_for_config():
    """Create a `blade` API module for the config phase."""
    return _safe_blade_module(config_phase=True)

