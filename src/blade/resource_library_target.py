# Copyright (c) 2013 Tencent Inc.
# All rights reserved.
#
# Author: Feng Chen <phongchen@tencent.com>


"""
Define resource_library target.
"""


from blade import build_manager
from blade import build_rules
from blade import cc_targets
from blade.blade_types import StrOrList, StrOrListOpt
from blade.util import regular_variable_name, var_to_list, var_to_list_or_none


class ResourceLibrary(cc_targets.CcTarget):
    """This class is used to generate C/C++ resource library rules."""

    def __init__(self,
                 name: 'str | None',
                 srcs: 'StrOrListOpt',
                 deps: 'StrOrListOpt',
                 visibility: 'StrOrListOpt',
                 tags: 'StrOrListOpt',
                 optimize: 'StrOrListOpt',
                 extra_cppflags: 'StrOrListOpt',
                 kwargs: 'dict[str, object]'):
        """Init method.

        Init the cc target.

        """
        # Normalize the BUILD-file-friendly StrOrList unions once, right at
        # the top; everything below (including CcTarget.__init__) sees the
        # layer-2 `list[str]` / `list[str] | None` shape.
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        tags = var_to_list(tags)
        extra_cppflags = var_to_list(extra_cppflags)
        visibility = var_to_list_or_none(visibility)
        optimize = var_to_list_or_none(optimize)
        super().__init__(
                name=name,
                type='resource_library',
                srcs=srcs,
                src_exts=[],
                deps=deps,
                visibility=visibility,
                tags=tags,
                warning='',
                defs=[],
                incs=[],
                export_incs=[],
                optimize=optimize,
                linkflags=None,
                extra_cppflags=extra_cppflags,
                extra_linkflags=[],
                kwargs=kwargs)
        hdr = '%s.h' % self.name
        self.attr['generated_hdrs'] = [self._target_file_path(hdr)]
        self._add_tags('lang:lexyacc', 'type:library')
        self._set_hdrs([hdr])

    def generate(self):
        self._check_deprecated_deps()
        if not self.srcs:
            return

        resources = [self._source_file_path(s) for s in self.srcs]
        index = [self._target_file_path('%s.h' % self.name),
                 self._target_file_path('%s.c' % self.name)]
        self.generate_build('resource_index', index, inputs=resources,
                            variables={
                                'name': regular_variable_name(self.name),
                                'path': self.path
                            })
        sources = ['%s.c' % self.name]
        for resource in self.srcs:
            generated_source = '%s.c' % resource
            self.generate_build('resource', self._target_file_path(generated_source),
                                inputs=self._source_file_path(resource))
            sources.append(generated_source)
        objs = self._generated_cc_objects(sources)
        self._cc_library(objs)


def resource_library(name: 'str | None' = None,
                     srcs: 'StrOrListOpt' = None,
                     deps: 'StrOrListOpt' = None,
                     visibility: 'StrOrListOpt' = None,
                     tags: 'StrOrListOpt' = None,
                     optimize: 'StrOrListOpt' = None,
                     extra_cppflags: 'StrOrListOpt' = None,
                     **kwargs: object) -> None:
    """resource_library."""
    target = ResourceLibrary(
            name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=tags,
            optimize=optimize,
            extra_cppflags=extra_cppflags,
            kwargs=kwargs)
    build_manager.instance.register_target(target)


build_rules.register_function(resource_library)
