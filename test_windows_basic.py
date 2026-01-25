#!/usr/bin/env python3

import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Test basic imports
try:
    from blade.toolchain import WindowsToolChain, BuildArchitecture
    print("✓ Toolchain import successful")
except Exception as e:
    print(f"✗ Toolchain import failed: {e}")
    sys.exit(1)

# Test architecture detection
try:
    win64_arch = BuildArchitecture.get_canonical_architecture('win64')
    print(f"✓ Windows architecture detection: win64 -> {win64_arch}")
except Exception as e:
    print(f"✗ Architecture detection failed: {e}")

# Test Windows toolchain creation (only on Windows)
if os.name == 'nt':
    try:
        toolchain = WindowsToolChain()
        print("✓ WindowsToolChain creation successful")
        
        # Test command detection
        cc, cxx, ld = toolchain.get_cc_commands()
        print(f"✓ MSVC commands detected: cc={cc}, cxx={cxx}, ld={ld}")
        
        # Test flag filtering
        gcc_flags = ['-Wall', '-O2', '-g']
        msvc_flags = toolchain.filter_cc_flags(gcc_flags)
        print(f"✓ Flag filtering: {gcc_flags} -> {msvc_flags}")
        
    except Exception as e:
        print(f"✗ WindowsToolChain failed: {e}")
else:
    print("ℹ Skipping Windows toolchain tests (not on Windows)")

# Test configuration
try:
    from blade import config
    print("✓ Config import successful")
except Exception as e:
    print(f"✗ Config import failed: {e}")

print("\n🎉 Basic functionality test completed!")