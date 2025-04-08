import util

import os
import unittest


class TestWhich(unittest.TestCase):
    def test_which(self):
        if os.name == 'nt':
            self.assertEqual(r'c:\windows\system32\cmd.exe', util.which('cmd').lower())
        else:
            self.assertEqual('/usr/bin/sh', util.which('sh'))

if __name__ == "__main__":
    unittest.main()
