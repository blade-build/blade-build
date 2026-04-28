# Copyright (c) 2016 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   June 2, 2016

"""
This module defines sh_test target which executes a shell script.
"""


import os

from blade import build_manager
from blade import build_rules
from blade.target import Target, LOCATION_RE
from blade.util import var_to_list


class ShellTest(Target):
    """
    ShellTest is derived from Target and used to execute a shell script.

    Normally by use of testdata you could establish test environment
    with all the necessary data and files placed in the runfiles directory
    and then refer to those files within the shell script directly.

    In addition to the regular files, the user is able to reference
    the output of another target in testdata using location references
    syntax.
    """

    def __init__(self,
                 name,
                 srcs,
                 deps,
                 visibility,
                 tags,
                 testdata,
                 kwargs):
        srcs = var_to_list(srcs)
        deps = var_to_list(deps)
        testdata = var_to_list(testdata)

        super().__init__(
                name=name,
                type='sh_test',
                srcs=srcs,
                src_exts=['sh', 'bash', ''],
                deps=deps,
                visibility=visibility,
                tags=tags,
                kwargs=kwargs)

        self._add_tags('lang:sh', 'type:test')
        self._process_test_data(testdata)

    def _process_test_data(self, testdata):
        """
        Process test data of which the source could be regular file
        or location reference.
        """
        self.attr['testdata'], self.attr['locations'] = [], []
        for td in testdata:
            if isinstance(td, tuple):
                src, dst = td
            elif isinstance(td, str):
                src, dst = td, ''
            else:
                self.error('Invalid testdata %s. Test data should be either str or tuple.' % td)
                continue

            m = LOCATION_RE.search(src)
            if m:
                key, type = self._add_location_reference_target(m)
                self.attr['locations'].append((key, type, dst))
            else:
                self.attr['testdata'].append(td)

    def generate(self):
        srcs = [self._source_file_path(s) for s in self.srcs]
        output = self._target_file_path(self.name)
        self.generate_build('shelltest', output, inputs=srcs)
        targets = self.blade.get_build_targets()
        inputs, testdata = [], []
        for key, type, dst in self.attr['locations']:
            path = targets[key]._get_target_file(type)
            if not path:
                self.warning('Location {} {} is missing. Ignored.'.format(key, type))
            else:
                inputs.append(path)
                if not dst:
                    testdata.append(os.path.basename(path))
                else:
                    testdata.append(dst)
        if inputs:
            output = self._target_file_path(self.name + '.testdata')
            self.generate_build('shelltestdata', output, inputs=inputs,
                                variables={'testdata': ' '.join(testdata)})


def sh_test(name=None,
            srcs=None,
            deps=[],
            visibility=None,
            tags=[],
            testdata=[],
            **kwargs):
    build_manager.instance.register_target(ShellTest(
            name=name,
            srcs=srcs,
            deps=deps,
            visibility=visibility,
            tags=[],
            testdata=testdata,
            kwargs=kwargs))


build_rules.register_function(sh_test)
