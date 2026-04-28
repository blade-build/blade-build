# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: chen3feng <chen3feng@gmail.com>
# Date:   Feb 12, 2021

"""
The ninja runner module.
"""


import os
import re
import subprocess
import time

from blade import console


def build(build_dir, build_script, jobs_num, targets, options):
    """Execute the ninja executable with proper arguments."""
    cmd = ['ninja', '-f', build_script]
    cmd += _build_options(options)
    cmd.append('-j%s' % jobs_num)
    if options.keep_going:
        cmd.append('-k0')
    if console.verbosity_compare(options.verbosity, 'verbose') >= 0:
        cmd.append('-v')
    if targets:
        cmd.append(targets)
    build_start_time = time.time()
    ret = _run_ninja_build(cmd, options)
    if options.show_builds_slower_than is not None:
        _show_slow_builds(build_dir, build_start_time, options.show_builds_slower_than)
    return ret


def dump_compdb(build_script, rules, output_file_name):
    """Dump the compdb to file."""
    cmd = ['ninja', '-f', build_script, '-t', 'compdb']
    cmd += rules
    cmdstr = subprocess.list2cmdline(cmd)
    cmdstr += ' > '
    cmdstr += output_file_name
    return _run_ninja_command(cmdstr)


def _build_options(options):
    """Setup some options which are same in different backend builders."""
    build_options = []
    if options.dry_run:
        build_options.append('-n')
    if options.backend_builder_options:
        build_options.append(options.backend_builder_options)
    return build_options


def _run_ninja_build(cmd, options):
    """Run the "ninja" program with interactive."""
    cmdstr = ' '.join(cmd)
    if console.verbosity_compare(options.verbosity, 'quiet') > 0:
        return _run_ninja_command(cmdstr)
    # In quiet mode, redirect ninja output to the file
    ninja_output = 'blade-bin/ninja_output.log'
    with open(ninja_output, 'w', buffering=1) as wf, open(ninja_output, buffering=1) as rf:
        os.environ['NINJA_STATUS'] = '[%f/%t] '  # The progress depends on this format
        p = subprocess.Popen(cmdstr, shell=True, stdout=wf, stderr=subprocess.STDOUT)
        _show_progress(p, rf)
    return p.returncode


def _run_ninja_command(cmdstr):
    """Run "ninja" command without interactive."""
    console.debug('Run build command: ' + cmdstr)
    p = subprocess.Popen(cmdstr, shell=True)
    try:
        p.wait()
        return p.returncode
    except KeyboardInterrupt:
        return 1


def _show_progress(process, file_reader):
    """
    Convert description message such as '[1/123] CC xxx.cc' into progress bar.
    """
    progress_re = re.compile(r'^\[(\d+)/(\d+)\]\s+')
    try:
        while True:
            process.poll()
            line = file_reader.readline().strip()
            if line:
                m = progress_re.match(line)
                if m:
                    console.show_progress_bar(int(m.group(1)), int(m.group(2)))
                else:
                    console.clear_progress_bar()
                    console.output(line)
            elif process.returncode is not None:
                break
            else:
                # Avoid cost too much cpu
                time.sleep(0.1)
    finally:
        console.clear_progress_bar()


def _show_slow_builds(build_dir, build_start_time, show_builds_slower_than):
    """Show slow build targets."""
    with open(os.path.join(build_dir, '.ninja_log')) as f:
        head = f.readline()
        if '# ninja log v5' not in head:
            console.warning('Unknown ninja log version: %s' % head)
            return
        build_times = []
        for line in f.readlines():
            start_time, end_time, timestamp, target, cmdhash = line.split()
            cost_time = (int(end_time) - int(start_time)) / 1000.0  # ms -> s
            timestamp = int(timestamp)
            if timestamp >= build_start_time and cost_time > show_builds_slower_than:
                build_times.append((cost_time, target))
        if build_times:
            console.notice('Slow build targets:')
            for cost_time, target in sorted(build_times):
                console.notice('{:.4g}s\t{}'.format(cost_time, target), prefix=False)
