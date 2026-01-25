# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Blade Team
# Date:   January 2025

"""Tests for Windows toolchain."""

import os
import sys

# Add src directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from blade.toolchain import WindowsToolChain, BuildArchitecture
import blade_test


class WindowsToolChainTest(blade_test.TargetTest):
    
    def setUp(self):
        if os.name != 'nt':
            self.skipTest("Windows-only test")
        self.toolchain = WindowsToolChain()
    
    def test_windows_architecture_detection(self):
        """Test Windows architecture detection."""
        arch = BuildArchitecture.get_canonical_architecture('win64')
        self.assertEqual(arch, 'win64')
        
        bits = BuildArchitecture.get_architecture_bits('win64')
        self.assertEqual(bits, '64')
        
        # Test model architecture
        model = BuildArchitecture.get_model_architecture('win64', '32')
        self.assertEqual(model, 'win32')
    
    def test_msvc_command_detection(self):
        """Test MSVC command detection."""
        cc, cxx, ld = self.toolchain.get_cc_commands()
        
        # On Windows, should detect cl.exe and link.exe
        self.assertTrue('cl' in cc.lower())
        self.assertEqual(cc, cxx)  # MSVC uses same compiler for C/C++
        self.assertTrue('link' in ld.lower())
    
    def test_msvc_version_detection(self):
        """Test MSVC version detection."""
        version = self.toolchain.get_cc_version()
        self.assertIsInstance(version, str)
        self.assertNotEqual(version, 'unknown')
    
    def test_msvc_vendor_detection(self):
        """Test MSVC vendor detection."""
        self.assertTrue(self.toolchain.cc_is('msvc'))
        self.assertFalse(self.toolchain.cc_is('gcc'))
    
    def test_msvc_flag_filtering(self):
        """Test MSVC flag filtering."""
        gcc_flags = ['-Wall', '-Wextra', '-O2', '-fPIC', '-g']
        msvc_flags = self.toolchain.filter_cc_flags(gcc_flags)
        
        # Should map GCC flags to MSVC equivalents
        self.assertIn('/W3', msvc_flags)  # -Wall -> /W3
        self.assertIn('/W4', msvc_flags)  # -Wextra -> /W4  
        self.assertIn('/O2', msvc_flags)  # -O2 -> /O2
        self.assertIn('/Zi', msvc_flags)  # -g -> /Zi
        
        # Should filter out Unix-specific flags
        self.assertNotIn('-fPIC', msvc_flags)


if __name__ == '__main__':
    unittest.main()