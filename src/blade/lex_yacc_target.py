# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: Feng Chen <phongchen@tencent.com>


"""
Define lex_yacc_library target.
"""


from blade import build_manager
from blade import build_rules
from blade.cc_targets import CcTarget
from blade.util import var_to_list


class LexYaccLibrary(CcTarget):
    """This class generates lex yacc rules."""

    def __init__(self,
                 name,
                 srcs,
                 deps,
                 visibility,
                 tags,
                 warning,
                 defs,
                 incs,
                 extra_cppflags,
                 extra_linkflags,
                 allow_undefined,
                 recursive,
                 prefix,
                 lexflags,
                 yaccflags,
                 kwargs):
        """Init method.

        Init the cc lex yacc target

        """
        super(LexYaccLibrary, self).__init__(
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
        name,
        srcs=[],
        deps=[],
        visibility=None,
        tags=[],
        warning='yes',
        defs=[],
        incs=[],
        extra_cppflags=None,
        extra_linkflags=None,
        allow_undefined=False,
        recursive=False,
        prefix=None,
        lexflags=[],
        yaccflags=[],
        **kwargs):
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
