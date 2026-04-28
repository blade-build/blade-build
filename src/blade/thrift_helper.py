# Copyright (c) 2012 iQIYI Inc.
# Copyright (c) 2013 Tencent Inc.
# Copyright (c) 2014 Huahang Liu
#
# All rights reserved.
#
# Author: Jingxu Chen <chenjingxu@qiyi.com>
#         Feng Chen <chen3feng@gmail.com>
#         Huahang Liu <liuhuahang@zerus.co>
#
# Date:   June 28, 2014

"""
Helper classes to get the files generated from thrift IDL files.

Additionally, FBThriftHelper works with the new thrift compiler
and library from Facebook's own branch:

    https://github.com/facebook/fbthrift

"""


import os
import re

from blade import console


class ThriftParser:
    def __init__(self, path):
        self.path = path
        if not os.path.isfile(self.path):
            console.error('"%s" is not a valid file.' % self.path)

        self.thrift_name = os.path.basename(self.path)[:-7]
        # Package name for each language.
        self.package_name = {}
        # Set to true if there is at least one const definition in the
        # thrift file.
        self.has_constants = False
        self.enums = []
        self.structs = []
        self.exceptions = []
        self.services = []

        # Parse the thrift IDL file.
        self._parse_file()

    def _parse_file(self):
        with open(self.path) as f:
            for line in f:
                line = line.strip()
                if line.startswith('//') or line.startswith('#'):
                    continue
                pos = line.find('//')
                if pos != -1:
                    line = line[:pos]
                pos = line.find('#')
                if pos != -1:
                    line = line[:pos]

                matched = re.match('^namespace ([0-9_a-zA-Z]+) ([0-9_a-zA-Z.]+)', line)
                if matched:
                    lang, package = matched.groups()
                    self.package_name[lang] = package
                    continue

                matched = re.match('(const|struct|service|enum|exception) ([0-9_a-zA-Z]+)', line)
                if not matched:
                    continue

                kw, name = matched.groups()
                if kw == 'const':
                    self.has_constants = True
                elif kw == 'struct':
                    self.structs.append(name)
                elif kw == 'service':
                    self.services.append(name)
                elif kw == 'enum':
                    self.enums.append(name)
                elif kw == 'exception':
                    self.exceptions.append(name)

        if self.has_constants or self.structs or self.enums or \
                self.exceptions or self.services:
            pass
        else:
            console.error('%s is an empty thrift file.' % self.path)


class FBThriftHelper(ThriftParser):
    def get_generated_cpp_files(self):
        files = ['gen-cpp/%s_constants.cpp' % self.thrift_name,
                 'gen-cpp/%s_constants.h' % self.thrift_name,
                 'gen-cpp/%s_reflection.cpp' % self.thrift_name,
                 'gen-cpp/%s_reflection.h' % self.thrift_name,
                 'gen-cpp/%s_types.cpp' % self.thrift_name,
                 'gen-cpp/%s_types.h' % self.thrift_name,
                 'gen-cpp/%s_types.tcc' % self.thrift_name]
        for service in self.services:
            files.append('gen-cpp/%s.cpp' % service)
            files.append('gen-cpp/%s.h' % service)
            files.append('gen-cpp/%s.tcc' % service)
        return files

    def get_generated_cpp2_files(self):
        files = ['gen-cpp2/%s_constants.cpp' % self.thrift_name,
                 'gen-cpp2/%s_constants.h' % self.thrift_name,
                 'gen-cpp2/%s_types.cpp' % self.thrift_name,
                 'gen-cpp2/%s_types.h' % self.thrift_name,
                 'gen-cpp2/%s_types.tcc' % self.thrift_name]
        for service in self.services:
            files.append('gen-cpp2/%s.cpp' % service)
            files.append('gen-cpp2/%s.h' % service)
            files.append('gen-cpp2/%s.tcc' % service)
        return files


class ThriftHelper(ThriftParser):
    def __init__(self, dir, src):
        super().__init__(os.path.join(dir, src))
        self.src = src

    def get_generated_cpp_files(self):
        thrift_name = self.src[:-7]
        files = ['%s_constants.cpp' % thrift_name,
                 '%s_constants.h' % thrift_name,
                 '%s_types.cpp' % thrift_name,
                 '%s_types.h' % thrift_name]
        dir = os.path.dirname(thrift_name)
        for service in self.services:
            files.append(os.path.join(dir, '%s.cpp' % service))
            files.append(os.path.join(dir, '%s.h' % service))

        return files

    def get_generated_java_files(self):
        java_package = ''
        if 'java' in self.package_name:
            java_package = self.package_name['java']
        base_path = os.path.join(*java_package.split('.'))

        files = []
        if self.has_constants:
            files.append('Constants.java')

        for enum in self.enums:
            files.append('%s.java' % enum)

        for struct in self.structs:
            files.append('%s.java' % struct)

        for exception in self.exceptions:
            files.append('%s.java' % exception)

        for service in self.services:
            files.append('%s.java' % service)

        files = [os.path.join(base_path, f) for f in files]
        return files

    def get_generated_py_files(self):
        py_package = self.thrift_name
        if 'py' in self.package_name:
            py_package = self.package_name['py']
        base_path = os.path.join(*py_package.split('.'))

        files = ['constants.py', 'ttypes.py']
        for service in self.services:
            files.append('%s.py' % service)

        files = [os.path.join(base_path, f) for f in files]
        return files
