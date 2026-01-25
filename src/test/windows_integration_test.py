# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Blade Team
# Date:   January 2025

"""Integration tests for Windows support."""

import unittest
import tempfile
import os
from blade import config
from blade.toolchain import WindowsToolChain


class WindowsIntegrationTest(unittest.TestCase):
    
    def setUp(self):
        if os.name != 'nt':
            self.skipTest("Windows-only test")
        
        # Create temporary directory for config
        self.temp_dir = tempfile.mkdtemp()
        config.initialize(self.temp_dir, False)
        
        # Setup Windows config
        config.windows_config(
            msvc_version='2022',
            cppflags=['/MD', '/EHsc'],
            warnings=['/W4'],
            optimize={
                'debug': ['/Od'],
                'release': ['/O2']
            }
        )
    
    def test_windows_config_loading(self):
        """Test Windows configuration loading."""
        windows_config = config.get_section('windows_config')
        self.assertEqual(windows_config['msvc_version'], '2022')
        self.assertIn('/MD', windows_config['cppflags'])
        self.assertIn('/EHsc', windows_config['cppflags'])
        self.assertIn('/W4', windows_config['warnings'])
        
        # Test optimize settings
        self.assertIn('/Od', windows_config['optimize']['debug'])
        self.assertIn('/O2', windows_config['optimize']['release'])
    
    def test_windows_toolchain_creation(self):
        """Test Windows toolchain creation and setup."""
        toolchain = WindowsToolChain()
        
        # Should detect MSVC tools
        self.assertIsNotNone(toolchain.cc)
        self.assertIsNotNone(toolchain.cxx)
        self.assertIsNotNone(toolchain.ld)
        self.assertIsNotNone(toolchain.ar)
        
        # C and C++ compilers should be the same for MSVC
        self.assertEqual(toolchain.cc, toolchain.cxx)
        
        # Should have version information
        self.assertIsNotNone(toolchain.cc_version)
    
    def test_windows_flag_translation(self):
        """Test flag translation from GCC to MSVC."""
        toolchain = WindowsToolChain()
        
        # Test common flag translations
        gcc_flags = ['-Wall', '-O2', '-g', '-DDEBUG']
        msvc_flags = toolchain.filter_cc_flags(gcc_flags)
        
        self.assertIn('/W3', msvc_flags)  # -Wall -> /W3
        self.assertIn('/O2', msvc_flags)  # -O2 -> /O2
        self.assertIn('/Zi', msvc_flags)  # -g -> /Zi
        self.assertIn('/DDEBUG', msvc_flags)  # -DDEBUG -> /DDEBUG
        
        # Should filter out unsupported flags
        self.assertNotIn('-fPIC', msvc_flags)
    
    def tearDown(self):
        """Clean up temporary directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()