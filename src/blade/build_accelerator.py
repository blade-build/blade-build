# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   August 02, 2012

"""
Build accelerator (ccache, distcc, etc.) manage module.
"""

from __future__ import absolute_import
from __future__ import print_function

import os


class BuildAccelerator(object):
    """Describe a build accelerator."""

    def __init__(self, toolchain):
        self.__toolchain = toolchain
        if os.name == 'nt':  # Windows
            self.__class__ = WindowsBuildAccelerator
            WindowsBuildAccelerator.__init__(self, toolchain)

    def get_cc_commands(self):
        """Get correct c/c++ commands with proper build accelerator prefix
        Returns:
            cc, cxx, linker
        """
        cc, cxx, ld = self.__toolchain.get_cc_commands()
        return cc, cxx, ld
    
    def get_ar_command(self):
        return self.__toolchain.get_ar()

    def adjust_jobs_num(self, cpu_core_num):
        # Calculate job numbers smartly
        return cpu_core_num


class WindowsBuildAccelerator(BuildAccelerator):
    """Windows build accelerator with MSVC support."""
    
    def __init__(self, toolchain):
        super(WindowsBuildAccelerator, self).__init__(toolchain)
        self.__toolchain = toolchain
    
    def get_cc_commands(self):
        """Get MSVC commands."""
        return self.__toolchain.get_cc_commands()
    
    def get_ar_command(self):
        """Get MSVC lib command."""
        return self.__toolchain.get_ar()
    
    def adjust_jobs_num(self, cpu_core_num):
        """Adjust job numbers for Windows."""
        # MSBuild works well with core count
        return cpu_core_num
