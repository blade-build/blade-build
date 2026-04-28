# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   August 02, 2012

"""
Build accelerator (ccache, distcc, etc.) manage module.
"""



class BuildAccelerator:
    """Describe a build accelerator."""

    def __init__(self, toolchain):
        self.__toolchain = toolchain

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
