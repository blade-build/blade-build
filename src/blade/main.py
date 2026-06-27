# Copyright 2011 Tencent Inc.
#
# Authors: Huan Yu <huanyu@tencent.com>
#          Feng Chen <phongchen@tencent.com>
#          Yi Wang <yiwang@tencent.com>
#          Chong Peng <michaelpeng@tencent.com>

"""
Main entrence of blade.
"""


import cProfile
import os
import pstats
import signal
import sys
import time
import traceback

from blade import build_attributes
from blade import build_manager
from blade import command_line
from blade import config
from blade import console
from blade import init_command
from blade import sanitizer
from blade import target_pattern
from blade import workspace
from blade.toolchain import BuildArchitecture, create_toolchain


def load_config(options, root_dir):
    """Load the configuration file and parse."""
    # Init global build attributes
    build_attributes.initialize(options)
    config.load_files(root_dir, options.load_local_config)


def setup_console(options):
    if options.color != 'auto':
        console.enable_color(options.color == 'yes')
    console.set_verbosity(options.verbosity)


def adjust_config_by_options(config, options):
    # Shared options between config and command line
    shared_options = {
        'global_config': ['debug_info_level', 'backend_builder', 'build_jobs', 'test_jobs', 'run_unrepaired_tests'],
        'java_config': ['jar_compression_level', 'fat_jar_compression_level'],
        'cc_config': ['fission', 'dwp'],
    }
    for section, names in shared_options.items():
        for name in names:
            value = getattr(options, name, None)
            if value is not None:
                getattr(config, section)(**{name: value})


def force_static_linkage_for_msan(options):
    """Under MemorySanitizer, force fully static linkage.

    MSan ships only a static runtime (there is no `libclang_rt.msan*.so`), so
    nothing in the process can be a shared library -- an instrumented `.so` can
    never resolve `__msan_*` at link time, and building one always fails. So
    force static both for the project's own libraries (`generate_dynamic`) and
    for how tests link their dependencies (`cc_test_config.dynamic_link`, which
    also drives `auto`-linkage vcpkg ports). Only override an option that was
    actually enabled, and tell the user we did. The other sanitizers have a
    shared runtime and are unaffected.

    Runs after `build_manager.initialize` so deferred (lambda) config values
    resolve, and before targets are loaded so the override takes effect.
    """
    if 'memory' not in sanitizer.parse(getattr(options, 'sanitizer', None)):
        return
    if config.get_item('cc_library_config', 'generate_dynamic'):
        console.notice('MemorySanitizer has no shared runtime; forcing '
                       'cc_library_config.generate_dynamic=False (static libraries)')
        config.cc_library_config(generate_dynamic=False)
    if config.get_item('cc_test_config', 'dynamic_link'):
        console.notice('MemorySanitizer requires static linking; forcing '
                       'cc_test_config.dynamic_link=False')
        config.cc_test_config(dynamic_link=False)


def _check_error_log(stage):
    """Check whether any error log occur during stage."""
    error_count = console.error_count()
    if error_count > 0:
        console.error(f'There are {error_count} errors in the {stage} stage')
        return 1
    return 0


def run_subcommand(blade_path, command, options, ws, toolchain, targets):
    """Run particular subcommands."""
    builder = build_manager.initialize(blade_path, command, options, ws, toolchain, targets)

    force_static_linkage_for_msan(options)

    # The 'dump' command is special, some kind of dump items should be ran before loading.
    if command == 'dump' and options.dump_config:
        output_file_name = os.path.join(ws.working_dir, options.dump_to_file)
        config.dump(output_file_name)
        return _check_error_log('dump')

    # Prepare the targets
    stages = [
        ('load', builder.load_targets),
        ('analyze', builder.analyze_targets),
    ]
    # vcpkg-managed install runs after analyze (which marks the demanded shared
    # ports) and BEFORE generate, so the installed artifacts exist on disk when
    # VcpkgLibrary resolves its lib filenames -- a port may add a debug postfix
    # (e.g. fmt's debug lib is fmtd.lib) that can't be predicted at parse time.
    # Only for building commands; query/clean/dump never install.
    if command in ('build', 'run', 'test'):
        stages.append(('vcpkg', builder.setup_vcpkg))
    stages.append(('generate', builder.generate))
    for stage, action in stages:
        action()
        if _check_error_log(stage):
            return 1
        if options.stop_after == stage:
            return 0

    # Run sub command
    returncode = getattr(builder, command)()
    if returncode != 0:
        return returncode
    return _check_error_log(command)


def run_subcommand_profile(blade_path, command, options, ws, toolchain, targets):
    """Run subcommand within profile."""
    pstats_file = os.path.join(ws.build_dir, 'blade.pstats')
    # NOTE: can't use an plain int variable to receive exit_code
    # because in python int is an immutable object, assign to it in the runctx
    # wll not modify the local exit_code.
    # so we use a mutable object list to obtain the return value of run_subcommand
    exit_code = [-1]
    cProfile.runctx(
        "exit_code[0] = run_subcommand(blade_path, command, options, ws, toolchain, targets)",
        globals(), locals(), pstats_file)
    p = pstats.Stats(pstats_file)
    p.sort_stats('cumulative').print_stats(20)
    p.sort_stats('time').print_stats(20)
    console.output('Binary profile file `%s` is also generated, '
                   'you can use `gprof2dot` or `vprof` to convert it to graph, eg:' % pstats_file)
    console.output('  gprof2dot.py -f pstats --color-nodes-by-selftime %s'
                   ' | dot -T pdf -o blade.pdf' % pstats_file)
    return exit_code[0]


def check_config(config):
    """Check the configuration."""
    if config.get_item('cc_config', 'dwp') and not config.get_item('cc_config', 'fission'):
        console.warning('`cc_config.dwp` is enabled but `cc_config.fission` is not, '
                        'dwp will not take effect without fission enabled')


def _main(blade_path, argv):
    """The main entry of blade."""
    command, options, targets = command_line.parse(argv)
    setup_console(options)

    # 'init' creates a new BLADE_ROOT, so it must run before workspace setup
    # (which requires an existing BLADE_ROOT).
    if command == 'init':
        return init_command.run_init(options)

    ws = workspace.initialize(options)

    # 'root' just prints the workspace root and exits, before any chdir /
    # config load / build setup. sys.exit short-circuits main() before the
    # trailing "Cost time" line, so stdout stays clean: cd "$(blade root)".
    if command == 'root':
        print(ws.root_dir)
        sys.exit(0)

    ws.switch_to_root_dir()
    load_config(options, ws.root_dir)

    adjust_config_by_options(config, options)

    check_config(config)

    if _check_error_log('config'):
        return 1

    if not targets:
        targets = ['.']
    targets = target_pattern.normalize_list(targets, ws.working_dir)

    # The selected cc toolchain is the single source of truth for the platform
    # triple (${os}/${arch}/${bits}); create it once, here, and pass it on. When
    # the deprecated -m flag is absent, arch/bits come from the toolchain too, so
    # the DSL (blade.arch) and prebuilt lib${bits} paths stay consistent.
    toolchain = create_toolchain(options.cc_toolchain)
    if not options.m:
        options.arch = toolchain.target_arch
        options.bits = BuildArchitecture.get_architecture_bits(toolchain.target_arch)

    ws.setup_build_dir(toolchain)

    lock_id = ws.lock()
    try:
        run_fn = run_subcommand_profile if options.profiling else run_subcommand
        return run_fn(blade_path, command, options, ws, toolchain, targets)
    finally:
        ws.unlock(lock_id)


def format_timedelta(seconds):
    """
    Format the time delta as human readable format such as '1h20m5s' or '5s' if it is short.
    """
    # We used to use the datetime.timedelta class, but its result such as
    #   Blade(info): cost time 00:05:30s
    # cause vim to create a new file named "Blade(info): cost time 00"
    # in vim QuickFix mode. So we use the new format now.
    mins = int(seconds // 60)
    seconds %= 60
    hours = mins // 60
    mins %= 60
    result = '%.3gs' % seconds
    if hours > 0 or mins > 0:
        result = '%sm' % mins + result
    if hours > 0:
        result = '%sh' % hours + result
    return result


def main(blade_path, argv):
    exit_code = 0
    try:
        start_time = time.monotonic()
        exit_code = _main(blade_path, argv)
        cost_time = time.monotonic() - start_time
        console.info('Cost time %s' % format_timedelta(cost_time))
    except SystemExit as e:
        # pylint misreport e.code as classobj
        exit_code = e.code
    except KeyboardInterrupt:
        console.error('KeyboardInterrupt')
        exit_code = -signal.SIGINT
    except Exception:
        exit_code = 1
        console.error(traceback.format_exc())
    if exit_code != 0:
        console.error('Failure')
    return exit_code
