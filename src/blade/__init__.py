"""Public API for user rules."""


# Default imports for user code
import blade.config
import blade.console

# For old code compatible
blade_util = blade.util

# pylint: disable=import-outside-toplevel


def workspace_root_dir():
    """Get the root dir of current workspace."""
    import blade.build_manager
    return blade.build_manager.instance.get_root_dir()


def current_source_dir():
    """Get current source dir (in which the current BUILD resides) relative to WORKSPACE root."""
    import blade.build_manager
    return blade.build_manager.instance.get_current_source_path()


def current_target_dir():
    """Get corresponding target dir of current source dir, such as build64_release/xxx."""
    import os
    import blade.build_manager
    return os.path.join(blade.build_manager.instance.get_build_dir(), current_source_dir())
