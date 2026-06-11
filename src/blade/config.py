# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   January 09, 2012


"""
This is the configuration parse module which parses
the BLADE_ROOT as a configuration file.
"""


import hashlib
import inspect
import os
import pprint
import re
import sys

from blade import build_attributes
from blade import console
from blade import constants
from blade.util import var_to_list, eval_file, exec_file_content, source_location


_MAVEN_SNAPSHOT_UPDATE_POLICY_VALUES = ['always', 'daily', 'interval', 'never']

_config_globals = {}


def config_rule(func):
    """Decorator used to register functions accessible in the configuration file"""
    _config_globals[func.__name__] = func
    return func


# Template defining all config sections, their default values, and types.
# Read-only — never modified at runtime. User-provided values are stored in
# ``BladeConfig.config``.
_CONFIG_TEMPLATE = {
    'global_config': {
        '__help__': 'Global Configuration',
        'build_path_template': 'build${bits}_${profile}',
        'duplicated_source_action': 'warning',
        'duplicated_source_action__help__': "Can be 'warning', 'error', 'none'",
        'test_timeout': 0,
        'test_timeout__help__':
            'Per-test timeout in seconds. 0 (default) or any '
            'non-positive value means unlimited.',
        'test_related_envs__help__':
            'Environment variables which need to see whether changed before incremental '
            'testing. regex is allowed',
        'test_related_envs': [],
        'backend_builder': 'ninja',
        'debug_info_level': 'mid',
        'build_jobs': 0,
        'build_jobs__help__': constants.HELP.build_jobs,
        'test_jobs': 0,
        'test_jobs__help__': 'The number of test jobs to run simultaneously',
        'run_unrepaired_tests': False,
        'run_unrepaired_tests__help__': constants.HELP.run_unrepaired_tests,
        'glob_error_severity': 'error',
        'glob_error_severity__help__': 'The severity of glob error, can be %s' % constants.SEVERITIES,
        'default_visibility': set(),
        'default_visibility__help__': 'Default visibility for targets that do not declare this attribute',
        'legacy_public_targets': set(),
        'legacy_public_targets__help__': 'List of targets with legacy public visibility',

        'restricted_dsl': True,
        'restricted_dsl__help__': 'Whether use the restricted SDL in BUILD languages',
        'unrestricted_dsl_dirs': set(),
        'unrestricted_dsl_dirs__help__': 'Dirs in which allow unrestrict python DSL',

    },

    'cc_config': {
        '__help__': 'C/C++ Configuration',
        'toolchain': '',
        'toolchain__help__': 'Default toolchain name, overridable via --cc-toolchain=',
        'extra_incs': [],
        'cppflags': [],
        'cflags': [],
        'cxxflags': [],
        'linkflags': [],
        'c_warnings': [],
        'cxx_warnings': [],
        'warnings': [],
        'no_warning_allowed_paths': [
            'thirdparty', 'third_party', 'third-party',
            '3rdparty', '3rd_party', 'vendor',
        ],
        'no_warning_allowed_paths__help__':
            "Path keywords under which \"warning='no'\" may be used without a "
            'misuse warning (substring match against the target path and srcs)',
        'optimize': [],
        'benchmark_libs': [],
        'benchmark_main_libs': [],
        'secretcc': '',
        'debug_info_levels': {
            'no': ['-g0'],
            'low': ['-g1'],
            'mid': ['-g'],
            'high': ['-g3'],
        },
        'fission': False,
        'dwp': False,
        'fission__help__': 'Whether to generate split dwarf debug info',
        # PIE posture for executables. blade compiles every TU with -fPIC so a
        # single object set can serve .a / .so / exe (compile once, link many),
        # but never touches -pie / -no-pie -- the resulting binary's PIE-ness is
        # whatever the toolchain's default link mode is. That varies (modern
        # gcc defaults to -pie, older / --disable-default-pie toolchains do
        # not), making the hardening posture non-reproducible. This knob pins
        # it at the link step on Linux. macOS executables are PIE by default
        # (and ld64 removed -no_pie) and MSVC has no PIC/PIE concept, so the
        # knob is a no-op there. See issue #1258.
        'pie': 'auto',
        'pie__help__': 'PIE posture for executable links (Linux only): "auto" '
            '(default; follows the toolchain default), "yes" (force -pie -- '
            'guaranteed ASLR), "no" (force -no-pie). No effect on macOS/MSVC.',
        # Pass -fno-semantic-interposition to the compiler so it can reference
        # and inline the current TU's own global symbols directly under -fPIC,
        # instead of routing every reference through the GOT to allow
        # LD_PRELOAD-style replacement of *exe-internal* symbols. Recovers
        # most of the -fPIE perf without forking the object set (we still need
        # -fPIC for .so reuse). Naming mirrors the GCC flag and CPython's
        # Py_HAVE_NO_SEMANTIC_INTERPOSITION.
        # Default True (= apply the optimization). GCC's own ELF default is
        # the conservative interposable behavior; this knob flips it.
        # Only emitted for GCC -- Clang/Apple Clang already default to
        # non-interposing AND fire `-Wunused-command-line-argument` for this
        # flag on the C++ driver, which `-Werror` projects can't accept.
        # MSVC has no concept.
        # LD_PRELOAD'd jemalloc/tcmalloc/sanitizers/libfaketime are NOT
        # affected -- they replace libc symbols, which are extern to your TU
        # and always go through PLT. Set this knob to False only if your
        # binary intentionally has app-internal symbols that must remain
        # LD_PRELOAD-overridable (plugin frameworks like Frida, in-app
        # function-patching tools). See issue #1258 and CPython's
        # libpython3.so adoption rationale.
        'no_semantic_interposition': True,
        'no_semantic_interposition__help__': 'Whether to pass '
            '-fno-semantic-interposition to GCC for the perf win '
            '(no-op on Clang/MSVC). Default True. Set False only for '
            'plugin/in-app hook frameworks that replace exe-internal '
            'symbols; standard malloc replacements (jemalloc/tcmalloc) '
            'are unaffected.',
        'hdr_dep_missing_severity': 'error',
        'hdr_dep_missing_severity__help__': 'The severity of the missing dependency on the '
            'library to which the header file belongs, can be %s' % constants.SEVERITIES,
        'hdr_dep_missing_suppress': {},
        'hdr_dep_missing_suppress__help__': 'Header deps missing suppress control, see docs for details',
        'allowed_undeclared_hdrs': set(),
        'allowed_undeclared_hdrs__help__': 'Allowed undeclared header files',
        'unused_deps_severity': 'warning',
        'unused_deps_severity__help__': 'Severity of the unused dependency check (a dep declared '
            'in "deps" none of whose public headers is directly included), can be %s. Defaults to '
            '"warning" (advisory); set to "error" to enforce, or "debug" to silence.'
            % constants.SEVERITIES,
        'unused_deps_suppress': {},
        'unused_deps_suppress__help__': 'Unused deps suppress control, a {target: [deps]} map of '
            'intentionally-kept deps to exempt from the unused dependency check',
    },

    'cc_library_config': {
        '__help__': 'C/C++ Library Configuration',
        'prebuilt_libpath_pattern': 'lib${bits}',
        'generate_dynamic': False,
        # DEPRECATED: use 'deterministic' and/or 'thin' instead.
        # Platform-specific flags (rcs/D/T) are now handled automatically.
        'arflags': ['rcs'],
        'deterministic': False,
        'thin': False,
        'hdrs_missing_severity': 'error',
        'hdrs_missing_suppress': set(),
        # Validate that a cc_library's declared deps cover every undefined
        # symbol it references, without requiring a shared-library link.
        # See issue #1225. EXPERIMENTAL -- the check ships on by default but at
        # `warning` severity so that any false-positives we haven't seen yet
        # surface as diagnostics without blocking builds. Flip severity to
        # `error` once you've confirmed the check is clean on your codebase.
        'check_undefined': True,
        'check_undefined__help__': 'EXPERIMENTAL. Whether to statically validate that '
            'declared deps cover every undefined symbol referenced by each cc_library. '
            'Default True; pair with check_undefined_severity to control the diagnostic.',
        'check_undefined_severity': 'warning',
        'check_undefined_severity__help__': 'Severity of an unresolved-symbol finding: '
            '"warning" (default) logs a warning and lets the build continue; "error" fails '
            'the build. Default is "warning" while the check is experimental.',
        # Global allowlist of symbols permitted to remain undefined. Each entry
        # is a Python regex matched with re.fullmatch against the mangled name
        # (what `nm -u` prints). System symbols (libc, libstdc++, weak refs)
        # are handled by an internal baseline; this list is for project-specific
        # symbols that are legitimately provided at final link time.
        'allow_undefined': [],
        'allow_undefined__help__': 'Global allowlist (regex patterns) of mangled symbol '
            'names permitted to remain undefined by the check_undefined static check.',
    },

    'cc_binary_config': {
        '__help__': 'C/C++ Executable Configuration',
        'extra_libs': [],
        'run_lib_paths': [],
    },

    'cc_test_config': {
        '__help__': 'C/C++ Test Configuration',
        'dynamic_link': False,
        'heap_check': '',
        'gperftools_libs': [],
        'gperftools_debug_libs': [],
        'gtest_libs': [],
        'gtest_main_libs': [],
        'pprof_path': '',
    },

    'link_config': {
        '__help__': 'Linking Configuration',
        'link_jobs': 0,
    },

    'cuda_config': {
        '__help__': 'CUDA Configuration',
        'cuda_path': '',
        'cu_warnings': [],
        'cuflags': [],
    },

    'java_config': {
        '__help__': 'Java Configuration',
        'version': '1.8',
        'source_version': '',
        'target_version': '',
        'fat_jar_conflict_severity': 'warning',
        'fat_jar_conflict_severity__help__':
            'The severity of java fat jar packing conflict, can be "debug", "warning", "error"',
        'maven': 'mvn',
        'maven_central': '',
        'maven_snapshot_update_policy': 'daily',
        'maven_snapshot_update_policy__help__':
            'Can be %s' % _MAVEN_SNAPSHOT_UPDATE_POLICY_VALUES,
        'maven_snapshot_update_interval': 0,
        'maven_snapshot_update_interval__help__': 'When policy is interval, in minutes',
        'maven_download_concurrency': 0,
        'maven_download_concurrency__help__': constants.HELP.maven_download_concurrency,
        'maven_jar_allowed_dirs': set(),
        'maven_jar_allowed_dirs__help__':
            'List of directories and their subdirectories where maven_jar is allowed',
        'maven_jar_allowed_dirs_exempts': set(),
        'maven_jar_allowed_dirs_exempts__help__':
            'List of targets which are exempted from maven_jar_disallowed_dirs check',
        'warnings': ['-Werror', '-Xlint:all'],
        'source_encoding': '',
        'java_home': '',
        'jar_compression_level': '',
        'jar_compression_level__help__': constants.HELP.jar_compression_level,
        'fat_jar_compression_level': "6",
        'fat_jar_compression_level__help__': constants.HELP.fat_jar_compression_level,
        'debug_info_levels': {
            'no': ['-g:none'],
            'low': ['-g:source'],
            'mid': ['-g:source,lines'],
            'high': ['-g'],
        },
    },

    'java_binary_config': {
        '__help__': 'Java Executable Configuration',
        'one_jar_boot_jar': '',
    },

    'java_test_config': {
        '__help__': 'Java Test Configuration',
        'junit_libs': [],
        'junit_libs__help__':
            'Labels of the JUnit runtime libraries to auto-inject '
            'into every java_test target (mirrors cc_test_config '
            'gtest_libs / scala_test_config scalatest_libs). Empty '
            'list means "no auto-injection"; each java_test must '
            'then list its JUnit runtime in `deps` explicitly.',
        'jacoco_home': '',
    },

    'scala_config': {
        '__help__': 'Scala Configuration',
        'scala_home': '',
        'target_platform': '',
        'warnings': '',
        'source_encoding': '',
    },

    'scala_test_config': {
        '__help__': 'Scala Test Configuration',
        'scalatest_libs': [],
    },

    'go_config': {
        '__help__': 'Golang Configuration',
        'go': '',
        'go_home': os.path.expandvars('$HOME/go'),  # GOPATH
        # enable go module for explicit use
        'go_module_enabled': os.environ.get("GO111MODULE") == "on",
        # onetree repository go module doesn't work in repository root
        'go_module_relpath': os.environ.get("go_module_relpath"),
    },

    'proto_library_config': {
        '__help__': 'Protobuf Configuration',
        'protoc': 'thirdparty/protobuf/bin/protoc',
        'protoc_java': '',
        'protobuf_libs': [],
        'protobuf_path': '',
        'protobuf_incs': [],
        'protobuf_cc_warning': '',
        'protobuf_java_incs': [],
        'protobuf_php_path': '',
        'protoc_php_plugin': '',
        'protobuf_java_libs': [],
        'protoc_go_plugin': '',
        'protoc_go_subplugins': [],
        # All the generated go source files will be placed
        # into $GOPATH/src/protobuf_go_path
        'protobuf_go_path': '',
        'protobuf_python_libs': [],
        'protoc_direct_dependencies': False,
        'well_known_protos': [],
        'extra_cppflags': [],
    },

    'protoc_plugin_config': {
        '__help__': 'Protobuf Plugin Configuration',
    },

    'thrift_config': {
        '__help__': 'Thrift Configuration',
        'thrift': 'thrift',
        'thrift_libs': [],
        'thrift_incs': [],
        'thrift_gen_params': 'cpp:include_prefix,pure_enums'
    },

    'lex_yacc_config': {
        '__help__': 'Lex/Yacc Configuration',
        # Override the binary used to generate scanner/parser sources. Defaults
        # are bare command names (Windows uses win_flex / win_bison from the
        # WinFlexBison project) so PATH lookup is the normal path. Set an
        # absolute path to pin a specific install, e.g. brew's keg-only bison
        # 3.x on macOS:
        #   lex_yacc_config(bison = '/opt/homebrew/opt/bison/bin/bison')
        'flex': 'win_flex --wincompat' if os.name == 'nt' else 'flex',
        'bison': 'win_bison' if os.name == 'nt' else 'bison',
    },

    # Multi-instance config pattern:
    #   1. Define a private template `_<section_name>` with defaults.
    #   2. Declare `<section_name>: {}` as an empty dict.
    #   3. In the @config_rule, copy the template, call
    #      _replace_config() to validate+apply kwargs, store by name.
    #   4. _dump_section() auto-detects dict-of-dicts sections;
    #      dump() skips keys starting with '_'.
    '_cc_toolchain_config': {
        '__help__': 'C/C++ Toolchain Configuration',
        'name': '',
        'kind': '',
        'target': '',
        'prefix': '',
        'tool_prefix': '',
        'cc': '',
        'cxx': '',
        'ld': '',
        'ar': '',
        'msvc_version': 'auto',
        'target_arch': 'auto',
    },

    'cc_toolchain_config': {},

    'msvc_config': {
        '__help__': 'MSVC-specific Configuration',
        'target_arch': 'auto',
        'target_arch__help__':
            'Target architecture: auto (detect from host), x64, x86, arm64, arm64ec',
        'msvc_version': 'auto',
        'msvc_version__help__': 'MSVC compiler version prefix (auto, 14.44, 14.51, ...)',
        'windows_sdk': 'auto',
        'windows_sdk__help__': 'Windows SDK version (auto, 10.0, etc.)',
        'visual_studio': 'auto',
        'visual_studio__help__': 'Visual Studio edition (auto, Community, Professional, Enterprise)',
        # /utf-8: read sources (and emit narrow literals) as UTF-8 instead of the
        #   system ANSI codepage -- avoids C4819 / miscompiled string literals.
        # /volatile:iso: standard ISO `volatile` (no implicit acquire/release
        #   fences), matching GCC/Clang; already the default on ARM64. Use
        #   std::atomic for cross-thread ordering.
        # The CRT flavor (/MD vs /MDd) is added per build profile in
        #   cc_rule_support, not hard-coded here.
        'cppflags': ['/utf-8', '/volatile:iso'],
        'cflags': [],
        # /EHsc: C++ exceptions (meaningless for C, so kept out of cppflags).
        # /Zc:__cplusplus: report the real __cplusplus value (otherwise stuck at
        #   199711L regardless of /std, breaking feature checks).
        # /bigobj: raise the COFF section limit -- avoids C1128 on heavily
        #   templated C++ (blade's COFF parser understands bigobj objects).
        'cxxflags': ['/EHsc', '/Zc:__cplusplus', '/bigobj'],
        'linkflags': ['/SUBSYSTEM:CONSOLE'],
        'warnings': ['/W3'],
        'optimize': {
            'debug': ['/Od'],
            'release': ['/O2'],
        },
        # Compiler debug-info flags per `global_config.debug_info_level`. /Z7
        # embeds CodeView in each .obj (parallel-safe under ninja, unlike the
        # PDB-server /Zi); the matching linker /DEBUG is added by the link rule.
        'debug_info_levels': {
            'no': [],
            'low': ['/Z7'],
            'mid': ['/Z7'],
            'high': ['/Z7'],
        },
    },

    # vcpkg package-manager integration (issue #1236). A single workspace-level
    # section: vcpkg's manifest model allows one version and one feature set per
    # package per workspace, so these map 1:1 onto vcpkg.json fields.
    'vcpkg_config': {
        '__help__': 'vcpkg C/C++ package manager configuration (issue #1236)',
        # True (default): blade orchestrates `vcpkg install` into a hermetic
        # tree under the build dir, using an overlay triplet that chainloads
        # blade's compiler. False: read artifacts the user installed themselves
        # under <root>/installed/<triplet> (root = vcpkg_config.root/$VCPKG_ROOT).
        'manage': True,
        # Pins the ports tree (git SHA or date) -> vcpkg.json "builtin-baseline".
        # Empty means unpinned (not reproducible); a warning is emitted later.
        'baseline': '',
        # The allow-list of packages: the single source of truth for what a
        # `vcpkg#<port>:<lib>` reference may resolve to. Each value is either a
        # version string ('fmt': '10.2.1') or a dict with version/features
        # ('curl': {'version': '8.5.0', 'features': ['ssl', 'http2']}).
        'packages': {},
        # Optional private registries -> vcpkg-configuration.json "registries".
        'registries': [],
        # vcpkg tool + ports tree. Empty = use $VCPKG_ROOT (a later phase may
        # bootstrap one when unset).
        'root': '',
        # Target triplet; 'auto' derives it from the resolved cc_toolchain.
        'triplet': 'auto',
        # Per-workspace install root, relative to the build dir.
        'install_dir': '.cache/vcpkg',
        # Binary-cache backend (the cross-workspace time-saver). 'auto' uses a
        # shared local dir; full vcpkg backend strings are accepted (later phase).
        'binary_cache': 'auto',
        # Governance: subtrees where bare `vcpkg#...` references are allowed.
        # Empty = anywhere (enforcement lands in a later phase).
        'direct_use_allowed': [],
    },

}


class _DeferredConfigValue:
    """Wraps a callable config value for later resolution at build time."""

    __slots__ = ('_func', '_expected_type', '_item_name')

    def __init__(self, func, expected_type: type, item_name: str):
        self._func = func
        self._expected_type = expected_type
        self._item_name = item_name


class _ConfigSectionView:
    """Lazy-resolving view of a config section.

    Resolves ``_DeferredConfigValue`` entries on access, not on creation.
    """

    _section: dict

    def __init__(self, section: dict):
        self._section = section

    def __getitem__(self, key):
        return _resolve_value(self._section[key])

    def __contains__(self, key):
        return key in self._section

    def __iter__(self):
        return iter(self._section)

    def __len__(self):
        return len(self._section)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self):
        return self._section.keys()

    def values(self):
        for k in self._section:
            yield self[k]

    def items(self):
        for k in self._section:
            yield k, self[k]


def _check_callable_arity(func, name: str) -> bool:
    """Validate that *func* accepts exactly 1 parameter."""
    try:
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
    except (ValueError, TypeError) as e:
        _blade_config.error(f'Cannot inspect signature of callable for "{name}": {e}')
        return False
    if len(params) != 1:
        _blade_config.error(
            f'Callable for "{name}" must accept exactly 1 parameter (the blade module), '
            f'but it accepts {len(params)}'
        )
        return False
    return True


def _resolve_value(value):
    """Resolve a deferred config value by calling it with the BUILD-time blade module.

    During the config phase (e.g. ``blade dump --config``), the build manager
    is not yet initialized and BUILD-only attributes such as ``cc_toolchain``
    are unavailable. In that case the function is returned as-is so dump can
    still complete.
    """
    if not isinstance(value, _DeferredConfigValue):
        return value
    from blade import build_manager
    if build_manager.instance is None:
        return value._func
    from blade import dsl_api
    blade = dsl_api.get_blade_module()
    result = value._func(blade)
    if not isinstance(result, value._expected_type):
        _blade_config.error(
            f'Function for "{value._item_name}" returned {type(result).__name__}, '
            f'expected {value._expected_type.__name__}'
        )
        return value._expected_type()
    return result


class BladeConfig:
    """BladeConfig. A configuration parser class."""

    def __init__(self):
        self.current_file_name = ''  # For error reporting
        self.__md5 = hashlib.md5()
        self.config = {}  # User-provided config values, keyed by section name

    def info(self, msg):
        console.info(f'{source_location(self.current_file_name)}: info: {msg}', prefix=False)

    def warning(self, msg):
        console.warning(f'{source_location(self.current_file_name)}: warning: {msg}', prefix=False)

    def error(self, msg):
        console.error(f'{source_location(self.current_file_name)}: error: {msg}', prefix=False)

    def fatal(self, msg):
        # NOTE: VSCode's problem matcher doesn't recognize 'fatal', use 'error' instead
        console.fatal(f'{source_location(self.current_file_name)}: error: {msg}', prefix=False)

    def try_parse_file(self, filename):
        """load the configuration file and parse."""
        try:
            self.current_file_name = filename
            if os.path.exists(filename):
                console.info('Loading config file "%s"' % filename)
                with open(filename, 'rb') as f:
                    content = f.read()
                    self.__md5.update(content)
                    exec_file_content(filename, content, _config_globals, None)
        except SystemExit:
            console.error('Parse error in config file %s' % filename)
        finally:
            self.current_file_name = ''

    def digest(self):
        """Hex md5 degest of all loaded config files"""
        return self.__md5.hexdigest()

    def update_config(self, section_name, append, user_config):
        """update config section by name."""
        section = self.get_section(section_name)
        if section is not None:
            if append:
                self._append_config(section_name, section, append)
            self._replace_config(section_name, section, user_config)
        else:
            self.error('%s: Unknown config section name' % section_name)

    def _append_config(self, section_name, section, append):
        """Append config section items"""
        self.warning('"append" is deprecated, please use the "append_" prefix to append')
        if not isinstance(append, dict):
            self.error('%s: Append must be a dict' % section_name)
        for k in append:
            if k in section:
                if isinstance(section[k], list):
                    section[k] += var_to_list(append[k])
                else:
                    self.warning(f'{section_name}: Config item {k} is not a list')

            else:
                self.warning(f'{section_name}: Unknown config item name: {k}')

    def _replace_config(self, section_name, section, user_config):
        """Replace config section items"""
        for name, value in user_config.items():
            if name in section:
                self._assign_item_value(section, name, value)
                continue
            if name.startswith('append_'):
                item_name = name[len('append_'):]
                if item_name in section:
                    self._append_item_value(section, name, item_name, value, user_config)
                    continue
            if name.startswith('prepend_'):
                item_name = name[len('prepend_'):]
                if item_name in section:
                    self._prepend_item_value(section, name, item_name, value, user_config)
                    continue
            msg = f'{section_name}: Unknown config item name: "{name}"'
            other_section = self.suggest_other_section(name)
            if other_section:
                msg += ', maybe it is in "%s"?' % other_section
            self.warning(msg)

    def _assign_item_value(self, section, name, value):
        """Assign value to config item. Supports callables for deferred evaluation."""
        if callable(value):
            if _check_callable_arity(value, name):
                current = section[name]
                if isinstance(current, _DeferredConfigValue):
                    expected_type = current._expected_type
                else:
                    expected_type = type(current)
                section[name] = _DeferredConfigValue(value, expected_type, name)
            return
        if isinstance(section[name], list):
            section[name] = var_to_list(value)
        elif isinstance(section[name], set):  # Allow using `list` to config `set`
            section[name] = set(var_to_list(value))
        elif isinstance(value, type(section[name])):
            section[name] = value
        else:
            self.error(f'Incorrect type for "{name}", expect "{type(section[name]).__name__}", actual "{type(value).__name__}"')

    def _append_item_value(self, section, name, item_name, value, user_config):
        """Append value to config item."""
        if item_name in user_config:
            self.error(f'"{name}" and "{item_name}" can not be used together')
            return
        if isinstance(section[item_name], list):
            section[item_name] += var_to_list(value)
        elif isinstance(section[item_name], set):
            section[item_name].update(var_to_list(value))
        else:
            self.warning(f'Invalid "{name}", "{item_name}" is not appendable')

    def _prepend_item_value(self, section, name, item_name, value, user_config):
        """Prepend value to config item."""
        if item_name in user_config:
            self.error(f'"{name}" and "{item_name}" can not be used together')
            return
        if isinstance(section[item_name], list):
            section[item_name] = var_to_list(value) + section[item_name]
        else:
            self.warning(f'Invalid "{name}", "{item_name}" is not prependable')

    def suggest_other_section(self, name):
        """Suggest possible section for item name"""
        for section_name, section in _CONFIG_TEMPLATE.items():
            if name in section:
                if name in section:
                    return section_name
            if name.startswith('append_'):
                item_name = name[len('append_'):]
            elif name.startswith('prepend_'):
                item_name = name[len('prepend_'):]
            else:
                continue
            if item_name in section:
                return section_name
        return ''

    def get_section(self, section_name):
        """Get config section, initializing from template on first access."""
        if section_name not in self.config:
            template = _CONFIG_TEMPLATE.get(section_name)
            if template is not None:
                self.config[section_name] = {k: v for k, v in template.items()}
            else:
                return None
        return self.config[section_name]

    def dump(self, output_file_name):
        with open(output_file_name, 'w') as f:
            print('# This config file was generated by `blade dump --config --to-file=<FILENAME>`\n', file=f)
            for name in sorted(_CONFIG_TEMPLATE):
                if name.startswith('_'):
                    continue
                section = self.get_section(name)
                if section is not None:
                    self._dump_section(name, section, f)

    def _dump_section(self, name, values, f):
        # Detect multi-instance: all non-__ values are dicts (named entries)
        entries = {k: v for k, v in values.items() if not k.startswith('__')}
        if entries and all(isinstance(v, dict) for v in entries.values()):
            help_text = values.get('__help__', '')
            for _entry_name, entry_values in entries.items():
                if help_text:
                    print('# %s' % help_text, file=f)
                self._dump_one_entry(name, entry_values, f)
            return

        self._dump_one_entry(name, values, f)

    def _dump_one_entry(self, func_name, values, f):
        help = '__help__'
        if help in values:
            print('# %s' % values[help], file=f)
        print('%s(' % func_name, file=f)
        for k, v in values.items():
            if k.endswith('__help__'):
                continue
            help = k + '__help__'
            if help in values:
                print('    # %s' % values[help], file=f)
            v = _resolve_value(v)
            print(f'    {k} = {pprint.pformat(v, indent=8)},', file=f)
        print(')\n', file=f)


# Global config object
_blade_config = BladeConfig()


def _compute_host_arch():
    """Canonical host CPU architecture: ``'x86_64'``, ``'aarch64'``, etc."""
    import platform
    machine = platform.machine()
    if machine.lower() in ('arm64', 'aarch64'):
        return 'aarch64'
    if machine.lower() in ('amd64', 'x86_64'):
        return 'x86_64'
    return machine.lower()


class _DeprecatedBuildTarget:
    """Deprecated wrapper for ``build_target`` — will be replaced by function-valued config items."""

    def __init__(self, target_attrs):
        object.__setattr__(self, '_target', target_attrs)
        object.__setattr__(self, '_warned', False)

    def _warn(self):
        if not self._warned:
            console.warning(
                'build_target is deprecated and will be removed in a future version. '
                'Its replacement will be provided via function-valued config items.'
            )
            object.__setattr__(self, '_warned', True)

    def __getattr__(self, name):
        self._warn()
        return getattr(self._target, name)


def load_files(blade_root_dir, load_local_config):
    from blade import dsl_api
    _config_globals['blade'] = dsl_api.new_blade_module_for_config()
    _config_globals['build_target'] = _DeprecatedBuildTarget(
        build_attributes.attributes
    )
    _blade_config.try_parse_file(os.path.join(os.path.dirname(sys.argv[0]), 'blade.conf'))
    _blade_config.try_parse_file(os.path.expanduser('~/.bladerc'))
    _blade_config.try_parse_file(os.path.join(blade_root_dir, 'BLADE_ROOT'))
    if load_local_config:
        _blade_config.try_parse_file(os.path.join(blade_root_dir, 'BLADE_ROOT.local'))


def digest():
    """Hex md5 digest of all loaded config files"""
    # Used in fingerprint entropy
    return _blade_config.digest()


def dump(output_file_name):
    _blade_config.dump(output_file_name)


def get_section(section_name):
    """Get a config section with all values resolved."""
    section = _blade_config.get_section(section_name)
    if section is None:
        return {}
    return {k: _resolve_value(v) for k, v in section.items()}


def get_item(section_name, item_name):
    """Get a resolved config item value."""
    return _resolve_value(_blade_config.get_section(section_name)[item_name])


def _check_kwarg_enum_value(kwargs, name, valid_values):
    value = kwargs.get(name)
    if value is not None and not callable(value) and value not in valid_values:
        _blade_config.error(f'Invalid config item "{name}" value "{value}", can only be in {valid_values}')


def _check_vcpkg_packages(packages):
    """Validate the shape of vcpkg_config.packages entries (issue #1236).

    Each value is either a version string or a dict with the keys ``version``
    and/or ``features`` (a list). The top-level dict type is enforced by the
    normal config machinery; this catches malformed per-port specs early.
    """
    if packages is None or callable(packages):
        return
    if not isinstance(packages, dict):
        _blade_config.error('vcpkg_config.packages must be a dict of {port: version|spec}')
        return
    for port, spec in packages.items():
        if isinstance(spec, str):
            continue
        if isinstance(spec, dict):
            unknown = set(spec) - {'version', 'features'}
            if unknown:
                _blade_config.error(
                    'vcpkg_config.packages["%s"]: unknown key(s) %s; allowed: version, features'
                    % (port, ', '.join(sorted(unknown))))
            features = spec.get('features')
            if features is not None and not isinstance(features, list):
                _blade_config.error(
                    'vcpkg_config.packages["%s"].features must be a list' % port)
            continue
        _blade_config.error(
            'vcpkg_config.packages["%s"] must be a version string or a dict with '
            'version/features, got "%s"' % (port, type(spec).__name__))


def _check_test_related_envs(kwargs):
    value = kwargs.get('test_related_envs')
    if value is None or callable(value):
        return
    for name in value:
        try:
            re.compile(name)
        except re.error as e:
            _blade_config.error(
                f'"global_config.test_related_envs": Invalid env name or regex "{name}", {e}')


def _check_default_visibility(kwargs):
    if 'default_visibility' not in kwargs:
        return
    value = kwargs['default_visibility']
    if callable(value):
        return
    value = var_to_list(value)
    if not value:
        return
    if len(value) != 1 or 'PUBLIC' not in value:
        _blade_config.error(
                '''"global_config.default_visibility" can only be empty("[]") or "['PUBLIC']"''')


_DUPLICATED_SOURCE_ACTION_VALUES = {'warning', 'error', 'none', None}


@config_rule
def load_value(filepath):
    """Safely evaluate containing literal from file."""
    return eval_file(filepath)


@config_rule
def config_items(**kwargs):
    """Used in config functions for config file, to construct a appended
    items dict, and then make syntax more pretty
    """
    return kwargs


@config_rule
def global_config(append=None, **kwargs):
    """global_config section."""
    _check_kwarg_enum_value(kwargs, 'duplicated_source_action', _DUPLICATED_SOURCE_ACTION_VALUES)
    debug_info_levels = _blade_config.get_section('cc_config')['debug_info_levels'].keys()
    _check_kwarg_enum_value(kwargs, 'debug_info_level', debug_info_levels)
    _check_test_related_envs(kwargs)
    _check_default_visibility(kwargs)
    _blade_config.update_config('global_config', append, kwargs)


@config_rule
def cc_test_config(append=None, **kwargs):
    """cc_test_config section."""
    _check_kwarg_enum_value(kwargs, 'heap_check', constants.HEAP_CHECK_VALUES)
    _blade_config.update_config('cc_test_config', append, kwargs)


@config_rule
def cc_binary_config(append=None, **kwargs):
    """cc_binary_config section."""
    _blade_config.update_config('cc_binary_config', append, kwargs)


@config_rule
def cc_library_config(append=None, **kwargs):
    """cc_library_config section."""
    has_arflags = 'arflags' in kwargs
    has_new = 'deterministic' in kwargs or 'thin' in kwargs
    if has_arflags and has_new:
        _blade_config.error(
            'cc_library_config: "arflags" and "deterministic"/"thin" cannot be used together')
    elif has_arflags:
        _blade_config.warning(
            'cc_library_config: "arflags" is deprecated, use "deterministic" and/or "thin" instead')
    if 'allow_undefined' in kwargs:
        _validate_allow_undefined(
            kwargs['allow_undefined'], 'cc_library_config.allow_undefined')
    _blade_config.update_config('cc_library_config', append, kwargs)


def _validate_allow_undefined(value, where):
    """Validate allow_undefined is a list of compilable regex patterns.

    The list form is only meaningful in cc_library_config (global) and on
    cc_library targets; bool form has its own meaning at the linker level
    and is not validated here. Patterns are compiled now so invalid regexes
    fail at config time, not at check time.
    """
    import re as _re
    if not isinstance(value, (list, tuple, set)):
        _blade_config.error('%s must be a list of regex patterns, got %r' % (where, type(value).__name__))
        return
    for p in value:
        if not isinstance(p, str):
            _blade_config.error('%s contains non-string entry: %r' % (where, p))
            continue
        try:
            _re.compile(p)
        except _re.error as e:
            _blade_config.error('%s contains invalid regex %r: %s' % (where, p, e))


_PIE_VALUES = ('auto', 'yes', 'no')


@config_rule
def cc_config(append=None, **kwargs):
    """extra cc config, like extra cpp include path splited by space."""
    _check_kwarg_enum_value(kwargs, 'hdr_dep_missing_severity', constants.SEVERITIES)
    _check_kwarg_enum_value(kwargs, 'pie', _PIE_VALUES)
    if 'extra_incs' in kwargs:
        extra_incs = kwargs['extra_incs']
        if isinstance(extra_incs, str) and ' ' in extra_incs:
            _blade_config.warning('"cc_config.extra_incs" has been changed to list')
            kwargs['extra_incs'] = extra_incs.split()
    _blade_config.update_config('cc_config', append, kwargs)


@config_rule
def link_config(append=None, **kwargs):
    """link_config."""
    _blade_config.update_config('link_config', append, kwargs)


@config_rule
def vcpkg_config(append=None, **kwargs):
    """vcpkg package-manager configuration (issue #1236).

    Workspace-level allow-list and infrastructure for ``vcpkg#<port>:<lib>``
    dependencies. Example::

        vcpkg_config(
            baseline = '2024-12-15',
            packages = {
                'fmt': '10.2.1',
                'curl': {'version': '8.5.0', 'features': ['ssl', 'http2']},
            },
        )
    """
    _check_vcpkg_packages(kwargs.get('packages'))
    _blade_config.update_config('vcpkg_config', append, kwargs)


@config_rule
def cuda_config(append=None, **kwargs):
    """cuda_config."""
    _blade_config.update_config('cuda_config', append, kwargs)


@config_rule
def java_config(append=None, **kwargs):
    """java_config."""
    _check_kwarg_enum_value(kwargs, 'maven_snapshot_update_policy',
                            _MAVEN_SNAPSHOT_UPDATE_POLICY_VALUES)
    _blade_config.update_config('java_config', append, kwargs)


@config_rule
def java_binary_config(append=None, **kwargs):
    """java_test_config."""
    _blade_config.update_config('java_binary_config', append, kwargs)


@config_rule
def java_test_config(append=None, **kwargs):
    """java_test_config."""
    _blade_config.update_config('java_test_config', append, kwargs)


@config_rule
def scala_config(append=None, **kwargs):
    """scala_config."""
    _blade_config.update_config('scala_config', append, kwargs)


@config_rule
def scala_test_config(append=None, **kwargs):
    """scala_test_config."""
    _blade_config.update_config('scala_test_config', append, kwargs)


@config_rule
def go_config(append=None, **kwargs):
    """go_config."""
    _blade_config.update_config('go_config', append, kwargs)


@config_rule
def proto_library_config(append=None, **kwargs):
    """protoc config."""
    path = kwargs.get('protobuf_include_path')
    if path:
        _blade_config.warning('proto_library_config: protobuf_include_path has '
                              'been renamed to protobuf_incs, and become a list')
        del kwargs['protobuf_include_path']
        if isinstance(path, str) and ' ' in path:
            kwargs['protobuf_incs'] = path.split()
        else:
            kwargs['protobuf_incs'] = [path]

    _blade_config.update_config('proto_library_config', append, kwargs)


@config_rule
def protoc_plugin(**kwargs):
    """protoc_plugin."""
    from blade.proto_library_target import ProtocPlugin  # pylint: disable=import-outside-toplevel
    if 'name' not in kwargs:
        _blade_config.error('Missing "name" in protoc_plugin parameters: %s' % kwargs)
        return
    section = _blade_config.get_section('protoc_plugin_config')
    section[kwargs['name']] = ProtocPlugin(**kwargs)


@config_rule
def thrift_library_config(append=None, **kwargs):
    """thrift config."""
    _blade_config.update_config('thrift_config', append, kwargs)


@config_rule
def lex_yacc_config(append=None, **kwargs):
    """lex/yacc config — primarily for pinning the flex/bison binaries.

    Example (macOS, brew's keg-only bison 3.x)::

        lex_yacc_config(bison = '/opt/homebrew/opt/bison/bin/bison')

    On Windows the win_flex / win_bison auto-detection in backend.py is used
    instead and these settings are not consulted.
    """
    _blade_config.update_config('lex_yacc_config', append, kwargs)


@config_rule
def fbthrift_library_config(append=None, **kwargs):
    """fbthrift config (deprecated)."""
    # fbthrift_library was removed in v3. This stub exists so that
    # BLADE_ROOT files referencing fbthrift_library_config don't
    # cause a NameError during config parsing. All arguments are
    # silently ignored.
    pass


_CC_TOOLCHAIN_KIND_VALUES = {'gcc', 'clang', 'msvc', 'mingw', 'cygwin'}


@config_rule
def cc_toolchain_config(**kwargs):
    """C/C++ toolchain configuration.

    Supports multiple named configs, selectable via ``--cc-toolchain=<name>``::

        cc_toolchain_config(name='gcc-13', kind='gcc', prefix='/opt/gcc-13')
        cc_toolchain_config(name='clang-17', kind='clang', prefix='/opt/clang-17')

    An unnamed config sets the default toolchain::

        cc_toolchain_config(kind='clang')
    """
    _check_kwarg_enum_value(kwargs, 'kind', _CC_TOOLCHAIN_KIND_VALUES)
    name = kwargs.get('name', '')
    section = _blade_config.get_section('cc_toolchain_config')
    if name in section:
        _blade_config.warning(
            f'cc_toolchain_config: duplicate name "{name or "(unnamed)"}", overwriting')
    template = _CONFIG_TEMPLATE['_cc_toolchain_config']
    entry = {k: v for k, v in template.items() if not k.startswith('__')}
    _blade_config._replace_config('cc_toolchain_config', entry, kwargs)
    section[name] = entry


@config_rule
def msvc_config(append=None, **kwargs):
    """msvc_config section. No-op on non-Windows platforms."""
    if os.name != 'nt':
        return
    _blade_config.update_config('msvc_config', append, kwargs)
