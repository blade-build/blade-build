#!/usr/bin/env python

"""
Collect the cc_library.hdrs missing reports and generate a suppress list.
You must run it from the root dir of the workspace.
"""

from __future__ import print_function

import os
import pprint
import re

# Example:
# 2021-02-11 17:36:21.172125 thirdparty/gtest/BUILD:3:0: info: gtest:
_PATTERN = re.compile(r'[\d-]+ [\d:.]+ (?P<path>[^:]+):.*: (?P<name>[^ ]+): No explicit "visibility" declaration')


def main():
    result = set()
    with open('blade-bin/blade.log') as log:
        for line in log:
            match = _PATTERN.match(line)
            if match:
                build = match.group('path')
                name = match.group('name')
                result.add(os.path.dirname(build) + ':' + name)
    pprint.pprint(sorted(result))


if __name__ == '__main__':
    main()
