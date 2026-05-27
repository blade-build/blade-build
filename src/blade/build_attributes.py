# Copyright (c) 2017 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   February 22, 2017

"""
This module defines the global build target attributes,
such as bits: 32/64, profile: debug/release.
"""

# Global target attributes object
attributes = None


class TargetAttributes:
    """Build target attributes."""

    def __init__(self, options):
        self.options = options

    @property
    def bits(self):
        return int(self.options.bits)

    @property
    def arch(self):
        return self.options.arch

    @property
    def os(self):
        """Target OS: ``'darwin'``, ``'linux'``, or ``'windows'``.

        Defaults to the host OS. Override via ``--target-os`` in the future.
        """
        import sys
        if sys.platform == 'win32':
            return 'windows'
        return sys.platform

    def is_debug(self):
        return self.options.profile == 'debug'


def initialize(options):
    global attributes
    attributes = TargetAttributes(options)
