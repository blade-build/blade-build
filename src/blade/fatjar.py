# Copyright (c) 2016 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   April 14, 2016

"""
This is the fatjar module which packages multiple jar files
into a single fatjar file.
"""


import os
import sys
import time
import traceback
import zipfile

from blade import console
from blade import util


_JAR_MANIFEST = 'META-INF/MANIFEST.MF'
_FATJAR_EXCLUSIONS = frozenset(['LICENSE', 'README', 'NOTICE',
                                'META-INF/LICENSE', 'META-INF/README',
                                'META-INF/NOTICE', 'META-INF/INDEX.LIST'])


def _is_signature_file(name):
    parts = name.upper().split('/')
    if len(parts) == 2:
        for suffix in ('.SF', '.DSA', '.RSA'):
            if parts[1].endswith(suffix):
                return True
        if parts[1].startswith('SIG-'):
            return True
    return False


def _is_fat_jar_excluded(name):
    name = name.upper()
    for exclusion in _FATJAR_EXCLUSIONS:
        if name.startswith(exclusion):
            return True

    return name == _JAR_MANIFEST or _is_signature_file(name)


def _manifest_scm(build_dir):
    revision, url = util.load_scm(build_dir)
    return [
        'SCM-Url: %s' % url,
        'SCM-Revision: %s' % revision,
    ]


def generate_fat_jar_metadata(jar, dependencies, conflicts):
    metadata_path = 'META-INF/blade'
    jar.writestr('%s/JAR.LIST' % metadata_path, '\n'.join(dependencies))
    content = ['[conflict]'] + conflicts
    jar.writestr('%s/MERGE-INFO' % metadata_path, '\n'.join(content))


def generate_fat_jar(output, conflict_severity, compression_level, args):
    """Generate a fat jar containing the contents of all the jar dependencies."""
    target = output
    jars = args

    target_dir = os.path.dirname(output)
    if not os.path.exists(target_dir):
        os.makedirs(target_dir)

    target_fat_jar = util.open_zip_file_for_write(target, compression_level)
    # Record paths written in the fat jar to avoid duplicate writing
    path_jar_dict = {}
    conflicts = []

    for dep_jar in jars:
        jar = zipfile.ZipFile(dep_jar, 'r')
        name_list = jar.namelist()
        for name in name_list:
            if name.endswith('/') or not _is_fat_jar_excluded(name):
                if name not in path_jar_dict:
                    target_fat_jar.writestr(name, jar.read(name))
                    path_jar_dict[name] = dep_jar
                else:
                    if name.endswith('/'):
                        continue
                    message = (f'{target}: Duplicate path {name} found in {{{os.path.basename(path_jar_dict[name])}, {os.path.basename(dep_jar)}}}')
                    # Always log all conflicts for diagnosis
                    console.debug(message)
                    if '/.m2/repository/' not in dep_jar:
                        # There are too many conflicts between maven jars,
                        # so we have to ignore them, only count source code conflicts
                        conflicts.append('\n'.join([
                            'Path: %s' % name,
                            'From: %s' % path_jar_dict[name],
                            'Ignored: %s' % dep_jar,
                        ]))
        jar.close()

    if conflicts:
        getattr(console, conflict_severity)('%s: Found %d conflicts when packaging.' % (target, len(conflicts)))
        if conflict_severity == 'error':
            raise RuntimeError('fat jar packing conflict')

    generate_fat_jar_metadata(target_fat_jar, jars, conflicts)

    contents = [
        'Manifest-Version: 1.0',
        'Created-By: Python.Zipfile (Blade)',
        'Built-By: %s' % os.getenv('USER'),
        'Build-Time: %s' % time.asctime(),
    ]
    contents += _manifest_scm(target.split(os.sep)[0])
    contents.append('\n')
    target_fat_jar.writestr(_JAR_MANIFEST, '\n'.join(contents))
    target_fat_jar.close()


def main():
    try:
        options, args = util.parse_command_line(sys.argv[1:])
        generate_fat_jar(args=args, **options)
    except Exception as e:  # pylint: disable=broad-except
        console.error(f'fatjar error: {e!s} {traceback.format_exc()}')
        sys.exit(1)


if __name__ == '__main__':
    main()
