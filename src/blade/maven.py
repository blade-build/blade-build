# Copyright (c) 2015 Tencent Inc.
# All rights reserved.
#
# Author: Li Wenting <wentingli@tencent.com>
# Date:   August 28, 2015

"""
This is the maven module which manages jar files downloaded
from maven repository.
"""


import os
import shutil
import subprocess
import threading
import time

import queue

from blade import config
from blade import console


def is_valid_id(id):
    """Check if id is valid."""
    parts = id.split(':')
    if len(parts) == 3:
        group, artifact, version = parts
        if group and artifact and version:
            return True
    return False


class MavenArtifact:
    """
    MavenArtifact represents a jar artifact and its transitive dependencies
    separated by colon in maven cache.
    """

    def __init__(self, path, deps):
        self.path = path
        self.deps = deps

    def __repr__(self):
        return repr(self.__dict__)


class MavenCache:
    """MavenCache. Manages maven jar files."""

    __instance = None

    @staticmethod
    def instance(log_dir):
        if not MavenCache.__instance:
            MavenCache.__instance = MavenCache(log_dir)
        return MavenCache.__instance

    def __init__(self, log_dir):
        """Init method."""

        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        self.__log_dir = log_dir
        #   key: (id, classifier, transitive)
        #     id: jar id in the format group:artifact:version
        #   value: an instance of MavenArtifact
        self.__jar_database = {}

        java_config = config.get_section('java_config')
        self.__maven = java_config.get('maven')
        self.__central_repository = java_config.get('maven_central')
        self._check_config()

        self.__snapshot_update_policy = java_config.get('maven_snapshot_update_policy')
        if self.__snapshot_update_policy == 'interval':
            interval = java_config.get('maven_snapshot_update_interval')
            if not interval:
                console.fatal('java_config: "maven_snapshot_update_interval" is required when '
                              '"maven_snapshot_update_policy" is "interval"')
            self.__snapshot_update_interval = interval * 60  # minutes
        else:
            self.__snapshot_update_interval = 86400

        # Local repository is set to the maven default directory
        # and could not be configured currently
        local_repository = '~/.m2/repository'
        self.__local_repository = os.path.expanduser(local_repository)

        # Download the snapshot artifact daily
        self.__build_time = time.time()

        self.__to_download = queue.Queue()

    def _artifact_dir(self, id):
        """Get dir for artifact within local repository."""
        group, artifact, version = id.split(':')
        return os.path.join(self.__local_repository,
                            group.replace('.', '/'), artifact, version)

    def _check_config(self):
        """Check whether maven is configured correctly."""
        if not self.__maven:
            console.fatal('MavenCache is not configured')

    def _is_file_expired(self, filename):
        """Check if the modification time of file is expired relative to build time."""
        return self.__build_time - os.path.getmtime(filename) > self.__snapshot_update_interval

    def _need_download(self, filename, version, logfile):
        if not os.path.isfile(os.path.join(filename)):
            return True
        if not version.endswith('-SNAPSHOT'):
            return False
        if self.__snapshot_update_policy == 'always':
            return True
        if self.__snapshot_update_policy == 'never':
            return False
        if not os.path.isfile(logfile):
            return True
        # Use the logfile's timestamp as the update time
        return self._is_file_expired(logfile)

    def _filename_base(self, artifact, version, classifier):
        if classifier:
            return artifact + '-' + version + '-' + classifier
        return artifact + '-' + version

    @staticmethod
    def _add_prefix(filename, prefix):
        """Add a prefix to filename if any."""
        if not prefix:
            return filename
        return prefix + '_' + filename

    def _download_jar(self, id, classifier, target):
        group, artifact, version = id.split(':')
        basename = self._filename_base(artifact, version, classifier)
        jar = basename + '.jar'

        # Write log to build dir temporarily, and move it into the artifact_dir after success.
        log_name = self._add_prefix('download.log', classifier)
        log_path = os.path.join(self.__log_dir, basename + '_' + log_name)
        artifact_dir = self._artifact_dir(id)
        target_log = os.path.join(artifact_dir, log_name)

        if not self._need_download(os.path.join(artifact_dir, jar), version, target_log):
            return True

        if classifier:
            id = f'{id}:{classifier}'
        target.info('Downloading maven_jar %s' % id)
        cmd = [self.__maven,
               'dependency:get',
               '-DgroupId=%s' % group,
               '-DartifactId=%s' % artifact,
               '-Dversion=%s' % version]
        if classifier:
            cmd.append('-Dclassifier=%s' % classifier)
        cmd += ['-e', '-X']  # More detailed debug message
        target.debug(subprocess.list2cmdline(cmd))
        with open(log_path, 'w') as logf:
            rc = subprocess.call(cmd, stdout=logf)
        if rc != 0:
            message = (f'Error downloading maven_jar {id}, see "{log_path}" for details.')
            # Rertry without transitive
            cmd.append('-Dtransitive=false')
            with open(log_path, 'a') as f:
                f.write('\n\nBlade: Retry without transitive dependencies\n\n')

            with open(log_path, 'a') as logf:
                rc = subprocess.call(cmd, stdout=logf)
            if rc != 0:
                target.error(message)
                return False
            target.warning('Downloaded maven_jar %s, but without its transitive dependencies.' % id)
        try:
            shutil.move(log_path, target_log)
        except OSError:
            # When multiple threads download same artifact
            pass

        return True

    def _download_dependency(self, id, classifier, target):
        group, artifact, version = id.split(':')
        artifact_dir = self._artifact_dir(id)
        classpath = self._add_prefix('classpath.txt', classifier)
        log = self._add_prefix('classpath.log', classifier)
        log = os.path.join(artifact_dir, log)
        if not self._need_download(os.path.join(artifact_dir, classpath), version, log):
            return True

        # if classifier:
        #     id = '%s:%s' % (id, classifier)
        #     # Currently analyzing dependencies of classifier jar
        #     # usually fails. Here when there is no classpath.txt
        #     # file but classpath.log exists, that means the failure
        #     # of analyzing dependencies last time
        #     if (not os.path.exists(os.path.join(artifact_dir, classpath))
        #         and os.path.exists(log)):
        #         return False

        target.info('Querying dependencies for maven_jar %s' % id)
        classpath_tmp = classpath + '.tmp'
        pom = os.path.join(artifact_dir, artifact + '-' + version + '.pom')
        cmd = [self.__maven,
               'dependency:build-classpath',
               '-DincludeScope=runtime',
               '-Dmdep.outputFile=%s' % classpath_tmp,
               '-e', '-X',
               '-f', pom]
        classpath = os.path.join(artifact_dir, classpath)
        classpath_tmp = os.path.join(artifact_dir, classpath_tmp)
        with open(log, 'w') as logf:
            rc = subprocess.call(cmd, stdout=logf)
        if rc != 0:
            target.warning(f'Failed to query dependencies of {id} , see "{log}" for details.')
            try:
                os.remove(classpath_tmp)
            except OSError:
                pass
            return False

        try:
            shutil.move(classpath_tmp, classpath)
        except OSError:
            # When multiple threads download same artifact
            pass

        return True

    def _download_artifact(self, id, classifier, transitive, target):
        """Download the specified jar and its transitive dependencies."""
        if not self._download_jar(id, classifier, target):
            self.__jar_database[(id, classifier, transitive)] = None
            return False

        group, artifact, version = id.split(':')
        artifact_dir = self._artifact_dir(id)
        jar = artifact + '-' + version + '.jar'
        if classifier:
            jar = artifact + '-' + version + '-' + classifier + '.jar'

        deps = ''
        if transitive:
            if not self._download_dependency(id, classifier, target):
                # Ignore dependency download error
                pass
            else:
                classpath = os.path.join(artifact_dir, self._add_prefix('classpath.txt', classifier))
                with open(classpath) as f:
                    # Read the first line
                    deps = f.readline()

        # Thread safe, see https://docs.python.org/3/glossary.html#term-global-interpreter-lock
        artifact = MavenArtifact(os.path.join(artifact_dir, jar), deps)
        self.__jar_database[(id, classifier, transitive)] = artifact
        return True

    def get_artifact(self, id, classifier, transitive, target):
        """get_artifact_from_database."""
        if (id, classifier, transitive) not in self.__jar_database:
            self._download_artifact(id, classifier, transitive, target)
        return self.__jar_database.get((id, classifier, transitive))

    def schedule_download(self, id, classifier, transitive, target):
        """Schedule an artifact to be downloaded"""
        self.__to_download.put((id, classifier, transitive, target))

    def download_all(self):
        """Download all needed maven artifacts"""
        concurrency = config.get_item('java_config', 'maven_download_concurrency')
        num_threads = min(self.__to_download.qsize(), concurrency)
        if num_threads == 0:
            return
        console.info('Downloading maven_jars, concurrency=%d ...' % num_threads)
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=self._download_worker)
            thread.start()
            threads.append(thread)
        try:
            self.__to_download.join()
        except KeyboardInterrupt:
            console.error('KeyboardInterrupt')
            while not self.__to_download.empty():
                try:
                    self.__to_download.get_nowait()
                except queue.Empty:
                    pass
        finally:
            console.debug('join threads')
            for thread in threads:
                thread.join()
            console.debug('join threads done')
            console.info('Downloading maven_jars done.')

    def _download_worker(self):
        """Download worker thread function"""
        while not self.__to_download.empty():
            try:
                id, classifier, transitive, target = self.__to_download.get_nowait()
            except queue.Empty:
                return
            if target.dependents:  # Only download really used artifacts
                self._download_artifact(id, classifier, transitive, target)
            self.__to_download.task_done()
