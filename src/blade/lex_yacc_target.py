# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: Feng Chen <phongchen@tencent.com>


"""
Define lex_yacc_library target.
"""


import glob
import os
import shutil

from blade import build_manager
from blade import build_rules
from blade import config
from blade import rule_registry
from blade.blade_types import StrOrListOpt
from blade.cc_targets import CcTarget
from blade.ninja_rule import NinjaRule
from blade.util import var_to_list, var_to_list_or_none


class LexYaccLibrary(CcTarget):
    """This class generates lex yacc rules."""

    def __init__(self,
                 name: str | None,
                 srcs: StrOrListOpt,
                 deps: StrOrListOpt,
                 visibility: StrOrListOpt,
                 tags: StrOrListOpt,
                 warning: str,
                 defs: StrOrListOpt,
                 incs: StrOrListOpt,
                 extra_cppflags: StrOrListOpt,
                 extra_linkflags: StrOrListOpt,
                 allow_undefined: bool,
                 recursive: bool,
                 prefix: str | None,
                 lexflags: StrOrListOpt,
                 yaccflags: StrOrListOpt,
                 kwargs: dict[str, object]):
        """Init method.

        Init the cc lex yacc target

        """
        # Normalize before forwarding to CcTarget.__init__
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        defs = var_to_list(defs)
        incs = var_to_list(incs)
        visibility = var_to_list_or_none(visibility)
        super().__init__(
                name=name,
                type='lex_yacc_library',
                srcs=srcs,
                src_exts=['l', 'y', 'll', 'yy'],
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning=warning,
                defs=defs,
                incs=incs,
                export_incs=[],
                optimize=None,
                linkflags=None,
                extra_cppflags=[],
                extra_linkflags=[],
                kwargs=kwargs)

        if (len(srcs) != 2 or
                (not (srcs[0].endswith('.l') or srcs[0].endswith('.ll'))) or
                (not (srcs[1].endswith('.y') or srcs[1].endswith('.yy')))):
            self.error('"lex_yacc_library.srcs"  must be a pair of [lex_file, yacc_file]')

        self.attr['recursive'] = recursive
        self.attr['prefix'] = prefix
        self.attr['lexflags'] = var_to_list(lexflags)
        self.attr['yaccflags'] = var_to_list(yaccflags)
        self.attr['prefix'] = prefix
        self.attr['extra_cppflags'] = var_to_list(extra_cppflags)
        self.attr['extra_linkflags'] = var_to_list(extra_linkflags)
        self.attr['allow_undefined'] = allow_undefined
        self.attr['link_all_symbols'] = True
        cc, h, cc_path, h_path = self._yacc_generated_files(self.srcs[1])
        self._set_hdrs(h)
        self.attr['generated_hdrs'] = [h_path]

    def _lex_flags(self):
        """Return lex flags according to the options."""
        lex_flags = list(self.attr['lexflags'])
        if self.attr.get('recursive'):
            lex_flags.append('-R')
        prefix = self.attr.get('prefix')
        if prefix:
            lex_flags.append('-P %s' % prefix)
        return lex_flags

    def _yacc_flags(self):
        """Return yacc flags according to the options."""
        yacc_flags = list(self.attr['yaccflags'])
        yacc_flags.append('-d')
        prefix = self.attr.get('prefix')
        if prefix:
            yacc_flags.append('-p %s' % prefix)
        return yacc_flags

    def _cc_source(self, source):
        if source.endswith('.l') or source.endswith('.y'):
            return source + '.c'
        if source.endswith('.ll') or source.endswith('.yy'):
            return source + '.cc'
        raise ValueError('Unknown source %s' % source)

    def _lex_vars(self):
        lex_flags = self._lex_flags()
        if lex_flags:
            return {'lexflags': ' '.join(lex_flags)}
        return {}

    def _yacc_vars(self):
        yacc_flags = self._yacc_flags()
        if yacc_flags:
            return {'yaccflags': ' '.join(yacc_flags)}
        return {}

    def _lex_generated_files(self, source):
        cc = self._cc_source(source)
        cc_path = self._target_file_path(cc)
        return cc, cc_path

    def _lex_rules(self, source, implicit_deps, vars):
        cc, cc_path = self._lex_generated_files(source)
        input = self._source_file_path(source)
        self.generate_build('lex', cc_path, inputs=input, implicit_deps=implicit_deps, variables=vars)
        return cc, cc_path

    def _yacc_generated_files(self, source):
        cc = self._cc_source(source)
        if cc.endswith('.c'):
            h = '%s.h' % cc[:-2]
        else:
            h = '%s.hh' % cc[:-3]
        cc_path = self._target_file_path(cc)
        h_path = self._target_file_path(h)
        return cc, h, cc_path, h_path

    def _yacc_rules(self, source, rule, vars):
        cc, h, cc_path, h_path = self._yacc_generated_files(source)
        input = self._source_file_path(source)
        self.generate_build('yacc', cc_path, inputs=input, implicit_outputs=h_path, variables=vars)
        return cc, cc_path, h_path

    def generate(self):
        lex_file, yacc_file = self.srcs
        yacc_cc, yacc_cc_path, yacc_h_path = self._yacc_rules(yacc_file, 'yacc',
                                                              vars=self._yacc_vars())
        lex_cc, lex_cc_path = self._lex_rules(lex_file, implicit_deps=[yacc_cc_path],
                                              vars=self._lex_vars())
        objs = self._generated_cc_objects([lex_cc, yacc_cc],
                                          generated_headers=self.attr['generated_hdrs'])
        self._cc_library(objs)


def lex_yacc_library(
        name: str,
        srcs: StrOrListOpt = None,
        deps: StrOrListOpt = None,
        visibility: StrOrListOpt = None,
        tags: StrOrListOpt = None,
        warning: str = 'yes',
        defs: StrOrListOpt = None,
        incs: StrOrListOpt = None,
        extra_cppflags: StrOrListOpt = None,
        extra_linkflags: StrOrListOpt = None,
        allow_undefined: bool = True,
        recursive: bool = False,
        prefix: str | None = None,
        lexflags: StrOrListOpt = None,
        yaccflags: StrOrListOpt = None,
        **kwargs: object):
    """lex_yacc_library."""
    target = LexYaccLibrary(
            name=name,
            srcs=srcs,
            deps=deps,
            warning=warning,
            visibility=visibility,
            tags=tags,
            defs=defs,
            incs=incs,
            extra_cppflags=extra_cppflags,
            extra_linkflags=extra_linkflags,
            allow_undefined=allow_undefined,
            recursive=recursive,
            prefix=prefix,
            lexflags=lexflags,
            yaccflags=yaccflags,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(lex_yacc_library)


def _find_win_bison_data_dir():
    for pattern in [
        os.path.join(os.path.dirname(shutil.which('win_bison') or ''), 'data'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''),
                     'Microsoft', 'WinGet', 'Packages',
                     'WinFlexBison*', 'data'),
    ]:
        matches = glob.glob(pattern)
        if matches and os.path.isdir(matches[0]):
            return matches[0]
    return None


def _generate_lex_yacc_rules(ctx):
    """Ninja rules for lex_yacc_library."""
    lex_yacc_config = ctx.config_section('lex_yacc_config')
    lex_cmd = lex_yacc_config['flex']
    yacc_cmd = lex_yacc_config['bison']
    # Windows-only: when the user hasn't overridden the bison command and we're
    # falling back to the platform default `win_bison`, sniff the WinFlexBison
    # data dir. win_bison invoked via the WinGet Links hardlink otherwise looks
    # for data/m4sugar/ next to the link itself instead of the real install dir.
    if os.name == 'nt' and yacc_cmd == 'win_bison':
        bison_data_dir = _find_win_bison_data_dir()
        if bison_data_dir:
            yacc_cmd = f'cmd /c set "BISON_PKGDATADIR={bison_data_dir}" && win_bison'
    ctx.emit_rule(NinjaRule(
        name='lex',
        command=f'{lex_cmd} ${{lexflags}} -o ${{out}} ${{in}}',
        description='LEX ${in}'))
    ctx.emit_rule(NinjaRule(
        name='yacc',
        command=f'{yacc_cmd} ${{yaccflags}} -o ${{out}} ${{in}}',
        description='YACC ${in}'))


rule_registry.register_rule_provider(
    _generate_lex_yacc_rules, order=rule_registry.ORDER_LEX_YACC, name='lex_yacc')
