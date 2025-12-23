# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: Michaelpeng <michaelpeng@tencent.com>
# Date:   January 09, 2012


"""
This is the configuration parse module which parses
the BLADE_ROOT as a configuration file.
"""

from __future__ import absolute_import
from __future__ import print_function

import hashlib
import os
import pprint
import re
import sys

from blade import build_attributes
from blade import console
from blade import constants
from blade.util import var_to_list, iteritems, eval_file, exec_file_content, source_location


_MAVEN_SNAPSHOT_UPDATE_POLICY_VALUES = ['always', 'daily', 'interval', 'never']

_config_globals = {}


def config_rule(func):
    """Decorator used to register functions accessible in the configuration file"""
    _config_globals[func.__name__] = func
    return func


class BladeConfig(object):
    """BladeConfig. A configuration parser class."""

    def __init__(self):
        self.current_file_name = ''  # For error reporting
        self.__md5 = hashlib.md5()

        # Support generate comments when dump the config by the special '__help__' convention.
        # __help__ field is for section
        # __help__ suffix of items are for items.
        self.configs = {
            'global_config': {
                '__help__': 'Global Configuration',
                'build_path_template': 'build${bits}_${profile}',
                'duplicated_source_action': 'warning',
                'duplicated_source_action__help__': "Can be 'warning', 'error', 'none'",
                'test_timeout': 0,
                'test_timeout__help__': 'In seconds',
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
                'extra_incs': [],
                'cppflags': [],
                'cflags': [],
                'cxxflags': [],
                'linkflags': [],
                'c_warnings': [],
                'cxx_warnings': [],
                'warnings': [],
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
                'hdr_dep_missing_severity': 'error',
                'hdr_dep_missing_severity__help__': 'The severity of the missing dependency on the '
                    'library to which the header file belongs, can be %s' % constants.SEVERITIES,
                'hdr_dep_missing_suppress': {},
                'hdr_dep_missing_suppress__help__': 'Header deps missing suppress control, see docs for details',
                'allowed_undeclared_hdrs': set(),
                'allowed_undeclared_hdrs__help__': 'Allowed undeclared header files',
            },

            'cc_library_config': {
                '__help__': 'C/C++ Library Configuration',
                'prebuilt_libpath_pattern': 'lib${bits}',
                'generate_dynamic': False,
                # Options passed to ar/ranlib to control how
                # the archive is created, such as, let ar operate
                # in deterministic mode discarding timestamps
                'arflags': ['rcs'],
                'ranlibflags': [],
                'hdrs_missing_severity': 'error',
                'hdrs_missing_suppress': set(),
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

            'fbthrift_config': {
                '__help__': 'Facebook Thrift Configuration',
                'fbthrift1': 'thrift1',
                'fbthrift2': 'thrift2',
                'fbthrift_libs': [],
                'fbthrift_incs': [],
            },
        }

    def info(self, msg):
        console.info('%s: info: %s' % (source_location(self.current_file_name), msg), prefix=False)

    def warning(self, msg):
        console.warning('%s: warning: %s' % (source_location(self.current_file_name), msg), prefix=False)

    def error(self, msg):
        console.error('%s: error: %s' % (source_location(self.current_file_name), msg), prefix=False)

    def fatal(self, msg):
        # NOTE: VSCode's problem matcher doesn't recognize 'fatal', use 'error' instead
        console.fatal('%s: error: %s' % (source_location(self.current_file_name), msg), prefix=False)

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
        section = self.configs.get(section_name)
        if section:
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
                    self.warning('%s: Config item %s is not a list' % (section_name, k))

            else:
                self.warning('%s: Unknown config item name: %s' % (section_name, k))

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
            msg = '%s: Unknown config item name: "%s"' % (section_name, name)
            other_section = self.suggest_other_section(name)
            if other_section:
                msg += ', maybe it is in "%s"?' % other_section
            self.warning(msg)


    def _assign_item_value(self, section, name, value):
        """Assign value to config item."""
        if isinstance(section[name], list):
            section[name] = var_to_list(value)
        elif isinstance(section[name], set):  # Allow using `list` to config `set`
            section[name] = set(var_to_list(value))
        elif isinstance(value, type(section[name])):
            section[name] = value
        else:
            self.error('Incorrect type for "%s", expect "%s", actual "%s"' % (
                name, type(section[name]).__name__, type(value).__name__))

    def _append_item_value(self, section, name, item_name, value, user_config):
        """Append value to config item."""
        if item_name in user_config:
            self.error('"%s" and "%s" can not be used together' % (name, item_name))
            return
        if isinstance(section[item_name], list):
            section[item_name] += var_to_list(value)
        elif isinstance(section[item_name], set):
            section[item_name].update(var_to_list(value))
        else:
            self.warning('Invalid "%s", "%s" is not appendable' % (name, item_name))

    def _prepend_item_value(self, section, name, item_name, value, user_config):
        """Prepend value to config item."""
        if item_name in user_config:
            self.error('"%s" and "%s" can not be used together' % (name, item_name))
            return
        if isinstance(section[item_name], list):
            section[item_name] = var_to_list(value) + section[item_name]
        else:
            self.warning('Invalid "%s", "%s" is not prependable' % (name, item_name))

    def suggest_other_section(self, name):
        """Suggest possible section for item name"""
        for section_name, section in self.configs.items():
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
        """get config section, returns default values if not set."""
        return self.configs[section_name]

    def dump(self, output_file_name):
        with open(output_file_name, 'w') as f:
            print('# This config file was generated by `blade dump --config --to-file=<FILENAME>`\n', file=f)
            for name, value in sorted(iteritems(self.configs)):
                self._dump_section(name, value, f)

    def _dump_section(self, name, values, f):
        help = '__help__'
        if help in values:
            print('# %s' % values[help], file=f)
        print('%s(' % name, file=f)
        for k, v in values.items():
            if k.endswith('__help__'):
                continue
            help = k + '__help__'
            if help in values:
                print('    # %s' % values[help], file=f)
            print('    %s = %s,' % (k, pprint.pformat(v, indent=8)), file=f)
        print(')\n', file=f)


# Global config object
_blade_config = BladeConfig()


def load_files(blade_root_dir, load_local_config):
    _config_globals['build_target'] = build_attributes.attributes
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
    return _blade_config.get_section(section_name)


def get_item(section_name, item_name):
    return _blade_config.get_section(section_name)[item_name]


def _check_kwarg_enum_value(kwargs, name, valid_values):
    value = kwargs.get(name)
    if value is not None and value not in valid_values:
        _blade_config.error('Invalid config item "%s" value "%s", can only be in %s' % (
            name, value, valid_values))


def _check_test_related_envs(kwargs):
    for name in kwargs.get('test_related_envs', []):
        try:
            re.compile(name)
        except re.error as e:
            _blade_config.error(
                '"global_config.test_related_envs": Invalid env name or regex "%s", %s' % (name, e))


def _check_default_visibility(kwargs):
    if 'default_visibility' not in kwargs:
        return
    value = var_to_list(kwargs['default_visibility'])
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
    _blade_config.update_config('cc_library_config', append, kwargs)


@config_rule
def cc_config(append=None, **kwargs):
    """extra cc config, like extra cpp include path splited by space."""
    _check_kwarg_enum_value(kwargs, 'hdr_dep_missing_severity', constants.SEVERITIES)
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
def fbthrift_library_config(append=None, **kwargs):
    """fbthrift config."""
    _blade_config.update_config('fbthrift_config', append, kwargs)
