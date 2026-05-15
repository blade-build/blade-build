#!/usr/bin/env python

"""
Dump the content of a pickle file.
such as the `incchk`, `blade-bin/blade_inclusion.data`, etc.
"""


import pprint
import sys

import pickle


def main():
    if len(sys.argv) < 2:
        print("Usage: %s <filepath>" % sys.argv[0])
        sys.exit(1)
    filename = sys.argv[1]
    content = pickle.load(open(filename, 'rb'))
    pprint.pprint(content)


if __name__ == '__main__':
    main()
