# -*- coding: utf-8 -*-
#
# Copyright (c) 2025 Tencent Inc.
# All rights reserved.
#
# Author: Deng Jian <jefferydeng@tencent.com>
# Date:   Dec 19, 2025

"""
DWP Wrapper Script for Blade-Build

This script wraps the dwp tool to intelligently collect .dwo files from
static libraries (.a files) and generate a .dwp file for the binary.

The script supports @file syntax to read inputs from a response file,
which is useful when the input list is very long and would exceed
command line length limits.

The script will:
1. Expand @file arguments to read inputs from response files
2. Extract .o file list from each .a file
3. Check if corresponding .dwo files exist
4. Collect .dwo files from binary's own object files
5. Call dwp tool to generate the final .dwp file
"""

from __future__ import print_function
import os
import sys
import tempfile

from blade import console
from blade import util

_IN_PY3 = sys.version_info[0] == 3


def expand_response_files(args):
    """
    Expand response files (@file) in the argument list.

    Args:
        args: List of arguments that may contain @file references

    Returns:
        list: Expanded list of arguments
    """
    expanded = []
    for arg in args:
        if not arg.startswith('@'):
            expanded.append(arg)
            continue
        # This is a response file
        rsp_path = arg[1:]
        try:
            with open(rsp_path, 'r') as f:
                # Read lines from response file
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        # Support multiple arguments per line
                        expanded.extend(line.split())
        except IOError as e:
            console.fatal("Error: Failed to read response file %s: %s" %
                    (rsp_path, e))
    return expanded


def extract_objects_from_archive(archive_path):
    """
    Extract the list of object files from a static library (.a file).

    Args:
        archive_path: Path to the .a file

    Returns:
        list: List of object file paths contained in the archive
    """
    # Use 'ar t' to list contents of the archive, 'ar t' outputs full paths
    returncode, stdout, stderr = util.run_command(['ar', 't', archive_path])
    if returncode != 0:
        console.fatal("Error: Failed to extract objects from %s with '%s'" % (archive_path, stderr))
    if _IN_PY3:
        stdout = stdout.decode('utf-8')

    object_files = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if line and line.endswith('.o'):
            # ar t already outputs the full path, use it directly
            object_files.append(line)

    return object_files


def find_dwo_for_object(obj_path):
    """
    Find the corresponding .dwo file for an object file.

    Args:
        obj_path: Path to the .o file

    Returns:
        str: Path to the .dwo file if it exists, None otherwise
    """
    # Replace .o extension with .dwo
    dwo_path = obj_path[:-2] + '.dwo'
    if os.path.exists(dwo_path):
        return dwo_path
    return None


def collect_dwo_files(inputs):
    """
    Collect all .dwo files from the given inputs.

    Args:
        inputs: List of input files (.a files, .o files, or .dwo files)

    Returns:
        list: List of .dwo file paths
    """
    dwo_files = []
    seen = set()  # To avoid duplicates

    for input_path in inputs:
        if not os.path.exists(input_path):
            console.warning("Warning: Input file does not exist: %s" % input_path)
            continue

        if input_path.endswith('.a'):
            # Static library: extract object files and find their .dwo files
            obj_files = extract_objects_from_archive(input_path)
            for obj_file in obj_files:
                dwo_file = find_dwo_for_object(obj_file)
                if dwo_file and dwo_file not in seen:
                    dwo_files.append(dwo_file)
                    seen.add(dwo_file)

        elif input_path.endswith('.o'):
            # Object file: find its .dwo file
            dwo_file = find_dwo_for_object(input_path)
            if dwo_file and dwo_file not in seen:
                dwo_files.append(dwo_file)
                seen.add(dwo_file)

        elif input_path.endswith('.dwo'):
            # Already a .dwo file
            if input_path not in seen:
                dwo_files.append(input_path)
                seen.add(input_path)

    return dwo_files


def run_dwp(output_path, dwo_files, dwp_tool='dwp'):
    """
    Run the dwp tool to generate the .dwp file.

    Args:
        output_path: Path to the output .dwp file
        dwo_files: List of .dwo files to include
        dwp_tool: Path to the dwp tool (default: 'dwp')
    """
    if not dwo_files:
        console.warning("Warning: No .dwo files found, skipping dwp generation")
        # Create an empty file to satisfy ninja
        open(output_path, 'w').close()
        return 0

    # Use a response file if there are many .dwo files
    if len(dwo_files) > 100:
        # Create a temporary response file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rsp',
                                         delete=False) as rsp_file:
            rsp_path = rsp_file.name
            for dwo_file in dwo_files:
                rsp_file.write(dwo_file + '\n')

        try:
            # Call dwp with response file
            cmd = [dwp_tool, '-o', output_path, '@' + rsp_path]
            console.debug("Running: %s" % ' '.join(cmd))
            console.debug("  with %d .dwo files" % len(dwo_files))
            return util.shell(cmd)
        finally:
            # Clean up response file
            try:
                os.unlink(rsp_path)
            except:  # pylint: disable=bare-except
                pass
    else:
        # Call dwp directly with all .dwo files
        cmd = [dwp_tool, '-o', output_path] + dwo_files
        console.debug("Running: %s" % ' '.join(cmd[:3] + ['...']))
        console.debug("  with %d .dwo files" % len(dwo_files))
        return util.shell(cmd)
