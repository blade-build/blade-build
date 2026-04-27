# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Authors: Huan Yu <huanyu@tencent.com>
#          Feng Chen <phongchen@tencent.com>
#          Yi Wang <yiwang@tencent.com>
#          Chong Peng <michaelpeng@tencent.com>
# Date: October 20, 2011


"""
This module executes the test programs.
"""


import datetime
import json
import os
import re
import time
from collections import namedtuple

from blade import binary_runner
from blade import config
from blade import console
from blade import coverage
from blade import target_pattern
from blade.test_scheduler import TestScheduler
# pylint: disable=unused-import
from blade.test_scheduler import TestRunResult  # Used by eval
from blade.util import md5sum


# Used by eval when loading test history
_TEST_HISTORY_FILE = '.blade.test.stamp'
_TEST_EXPIRE_TIME = 86400  # 1 day


TestJob = namedtuple('TestJob',
                     ['reason', 'binary_md5', 'testdata_md5', 'env_md5', 'args'])
TestHistoryItem = namedtuple('TestHistoryItem', [
    'job',  # TestJob
    'first_fail_time',
    'fail_count',
    'result',  # TestRunResult
])


def _filter_envs(names):
    """Filter names which matches `global_config.test_related_envs`"""
    related_names = config.get_item('global_config', 'test_related_envs')
    if not related_names:
        return []
    rx = '(' + '|'.join(['(%s)' % name for name in related_names]) + ')$'
    names_rx = re.compile(rx)
    return [name for name in names if names_rx.match(name)]


def _diff_env(a, b):
    """Return difference of two environments dict"""
    seta = set(a.items())
    setb = set(b.items())
    return dict(seta - setb), dict(setb - seta)


class TestRunner(binary_runner.BinaryRunner):
    """Run specified tests and collect the results"""
    def __init__(
            self,
            options,
            target_database,
            direct_targets,
            command_targets,
            build_targets,
            exclude_tests,
            test_jobs_num):
        """Init method.
        Args:
            test_jobs_num:int, max number of concurrent test jobs
        """
        # pylint: disable=too-many-locals, too-many-statements
        super(TestRunner, self).__init__(options, target_database, build_targets)
        self.__direct_targets = direct_targets
        self.__command_targets = command_targets
        self.__test_jobs_num = test_jobs_num

        # Test jobs should be run
        self.test_jobs = {}  # dict{key : TestJob}

        self.exclude_tests = exclude_tests  # Tests to be excluded
        self.excluded_tests = []  # Tests been excluded
        self.unchanged_tests = []
        self.unrepaired_tests = []
        self.repaired_tests = []
        self.new_failed_tests = []

        # Test history is the key to implement incremental test.
        # It will be loaded from file before test, compared with test jobs,
        # and be updated and saved to file back after test.
        self.test_history_file = os.path.join(self.build_dir, _TEST_HISTORY_FILE)
        self.test_history = {}  # {key, dict{}}

        self._load_test_history()
        self._update_test_history()

    def _load_test_history(self):
        if os.path.exists(self.test_history_file):
            with open(self.test_history_file) as f:
                try:
                    # pylint: disable=eval-used
                    self.test_history = eval(f.read())
                except (SyntaxError, NameError, TypeError) as e:
                    console.debug('Exception when loading test history: %s' % e)
                    console.warning('Error loading incremental test history, will run full test')

        if 'items' not in self.test_history:
            self.test_history['items'] = {}

    def _update_test_history(self):
        old_env = self.test_history.get('env', {})
        env_keys = _filter_envs(os.environ.keys())
        new_env = dict((key, os.environ[key]) for key in env_keys)
        if old_env and new_env != old_env:
            console.notice('Some tests will be run due to test environments changed:')
            new, old = _diff_env(new_env, old_env)
            if new:
                console.notice('New environments: %s' % new)
            if old:
                console.notice('Old environments: %s' % old)

        self.test_history['env'] = new_env
        self.env_md5 = md5sum(str(sorted(new_env.items())))

    def _save_test_history(self, passed_run_results, failed_run_results):
        """update test history and save it to file."""
        self._merge_passed_run_results_to_history(passed_run_results)
        self._merge_failed_run_results_to_history(failed_run_results)
        with open(self.test_history_file, 'w') as f:
            print(str(self.test_history), file=f)

    def _save_test_summary(self, passed_run_results, failed_run_results):
        with open('blade-bin/.blade-test-summary.json', 'w') as f:
            history_items = self.test_history['items']

            def expand(tests):
                ret = {}
                for key in tests:
                    history = history_items[key]
                    result = history.result._asdict()
                    history = history._asdict()
                    history.pop('job')
                    # flatten to upper level
                    history.pop('result')
                    history.update(result)
                    ret[key] = history
                return ret

            summary = {
                'time': time.time(),
                'passed': expand(passed_run_results),
                'failed': expand(failed_run_results),
                'unrepaired': expand(self.unrepaired_tests),
                'repaired': self.repaired_tests,
                'unchanged': self.unchanged_tests,
                'excluded': self.excluded_tests,
            }
            json.dump(summary, f, indent=4)

    def _merge_passed_run_results_to_history(self, run_results):
        history_items = self.test_history['items']
        for key, run_result in run_results.items():
            old = history_items.get(key)
            if old and old.result.exit_code != 0:
                self.repaired_tests.append(key)
            history_items[key] = TestHistoryItem(
                    self.test_jobs[key],
                    first_fail_time=0,
                    fail_count=0,
                    result=run_result)

    def _merge_failed_run_results_to_history(self, run_results):
        history_items = self.test_history['items']
        for key, run_result in run_results.items():
            old = history_items.get(key)
            if old:
                first_fail_time = old.first_fail_time or run_result.start_time
                fail_count = 1 if old.fail_count is None else old.fail_count + 1
            else:
                first_fail_time = run_result.start_time
                fail_count = 1
            if not old or old.result.exit_code == 0:
                self.new_failed_tests.append(key)

            history_items[key] = TestHistoryItem(
                    self.test_jobs[key],
                    first_fail_time=first_fail_time,
                    fail_count=fail_count,
                    result=run_result)

    def _get_test_target_md5sum(self, target):
        """Get test target md5sum."""
        # pylint: disable=too-many-locals
        related_file_list = []
        related_file_data_list = []
        test_file_name = os.path.abspath(self._executable(target))
        if os.path.exists(test_file_name):
            related_file_list.append(test_file_name)

        if target.attr.get('dynamic_link'):
            for dep in self._build_targets[target.key].expanded_deps:
                dep_target = self._build_targets[dep]
                if 'cc_library' in dep_target.type:
                    lib_name = 'lib%s.so' % dep_target.name
                    lib_path = os.path.join(self.build_dir,
                                            dep_target.path,
                                            lib_name)
                    abs_lib_path = os.path.abspath(lib_path)
                    if os.path.exists(abs_lib_path):
                        related_file_list.append(abs_lib_path)

        for i in target.attr['testdata']:
            if isinstance(i, tuple):
                data_target = i[0]
            else:
                data_target = i
            if '..' in data_target:
                continue
            if data_target.startswith('//'):
                data_target = data_target[2:]
                data_target_path = os.path.abspath(data_target)
            else:
                data_target_path = os.path.abspath('%s/%s' % (
                                                   target.path, data_target))
            if os.path.exists(data_target_path):
                related_file_data_list.append(data_target_path)

        related_file_list.sort()
        related_file_data_list.sort()

        test_target = []
        test_target_data = []
        for f in related_file_list:
            test_target.append(str(os.path.getmtime(f)))
            test_target.append(str(os.path.getctime(f)))

        for f in related_file_data_list:
            test_target_data.append(str(os.path.getmtime(f)))
            test_target_data.append(str(os.path.getctime(f)))
        return md5sum(''.join(test_target)), md5sum(''.join(test_target_data))

    def _exclude_test(self, target):
        """Whether exclude this test"""
        if not self.exclude_tests:
            return False
        for pattern in self.exclude_tests:
            if target_pattern.match(target.key, pattern):
                return True
        return False

    def _run_reason(self, target, history, binary_md5, testdata_md5):
        """Return run reason for a given test"""

        if self.options.full_test:
            return 'FULL_TEST'

        if target.attr.get('always_run'):
            return 'ALWAYS_RUN'
        if target.key in self.__direct_targets:
            return 'EXPLICIT'

        if not history:
            return 'NO_HISTORY'

        last_time = history.result.start_time
        interval = time.time() - last_time
        if interval >= _TEST_EXPIRE_TIME or interval < 0:
            return 'STALE'

        if history.job.binary_md5 != binary_md5:
            return 'BINARY'
        if history.job.testdata_md5 != testdata_md5:
            return 'TESTDATA'
        if history.job.env_md5 != self.env_md5:
            return 'ENVIRONMENT'
        if history.job.args != self.options.args:
            return 'ARGUMENT'

        if history.result.exit_code != 0:
            if config.get_item('global_config', 'run_unrepaired_tests'):
                return 'FAILED'
            if history.fail_count <= 1:
                return 'RETRY'

        return None

    def _collect_test_jobs(self):
        """Get incremental test run list."""
        for target in self._build_targets.values():
            if not target.type.endswith('_test'):
                continue
            if self._exclude_test(target):
                target.info('is skipped due to --exclude-test')
                self.excluded_tests.append(target.key)
                continue

            binary_md5, testdata_md5 = self._get_test_target_md5sum(target)
            history = self.test_history['items'].get(target.key)
            reason = self._run_reason(target, history, binary_md5, testdata_md5)
            if reason:
                self.test_jobs[target.key] = TestJob(
                        reason=reason,
                        binary_md5=binary_md5,
                        testdata_md5=testdata_md5,
                        env_md5=self.env_md5,
                        args=self.options.args)
            else:
                if history.result.exit_code == 0:
                    self.unchanged_tests.append(target.key)
                else:
                    self.unrepaired_tests.append(target.key)
        self.unrepaired_tests.sort(key=lambda x: self.test_history['items'][x].first_fail_time,
                                   reverse=True)

    def _generate_coverage_report(self):
        reporter = coverage.JacocoReporter(self.build_dir,
                                           self.target_database,
                                           self.__command_targets,
                                           self.test_jobs)
        reporter.generate()

    def _show_banner(self, text):
        pads = int((76 - len(text)) / 2)
        console.notice('{0} {1} {0}'.format('=' * pads, text), prefix=False)

    def _is_full_success(self, passed_run_results):
        return len(passed_run_results) == len(self.test_jobs) + len(self.unrepaired_tests)

    def _show_tests_list(self, tests, kind, level='info'):
        """Show tests list."""
        output = getattr(console, level)
        if tests:
            output('There are %d %s tests:' % (len(tests), kind))
            for key in sorted(tests):
                output('  %s' % key, prefix=False)

    def _show_run_results(self, run_results, is_error=False):
        """Show the tests detail after scheduling them."""
        tests = []
        for key, result in run_results.items():
            reason = self.test_jobs[key].reason
            tests.append((key, result.cost_time, reason, result.exit_code))
        tests.sort(key=lambda x: x[1])
        output_function = console.error if is_error else console.info
        for key, costtime, reason, result in tests:
            output_function('  %s triggered by %s, exit(%s), cost %.2f s' % (
                            key, reason, result, costtime), prefix=False)

    def _show_unrepaired_results(self):
        """Show the unrepaired tests"""
        if not self.unrepaired_tests:
            return
        items = self.test_history['items']
        console.error('Skipped %d still unrepaired tests:' % len(self.unrepaired_tests))
        for key in self.unrepaired_tests:
            test = items[key]
            first_fail_time = time.strftime('%F %T %A', time.localtime(test.first_fail_time))
            duration = datetime.timedelta(seconds=int(time.time() - test.first_fail_time))
            console.error('  %s: exit(%s), retry %s times, since %s, duration %s' % (
                key, test.result.exit_code, test.fail_count, first_fail_time, duration),
                prefix=False)
        console.error('You can specify --run-unrepaired-tests to run them', prefix=False)

    def _collect_slow_tests(self, run_results):
        return [(result.cost_time, key) for key, result in run_results.items()
                if result.cost_time > self.options.show_tests_slower_than]

    def _show_slow_tests(self, passed_run_results, failed_run_results):
        slow_tests = (self._collect_slow_tests(passed_run_results) +
                      self._collect_slow_tests(failed_run_results))
        if slow_tests:
            console.warning('Found %d slow tests:' % len(slow_tests))
            for cost_time, key in sorted(slow_tests):
                console.warning('  %.4gs\t//%s' % (cost_time, key), prefix=False)

    def _show_tests_summary(self, passed_run_results, failed_run_results):
        """Show tests summary."""
        self._show_banner('Testing Summary')
        console.info('%d tests scheduled to run by scheduler.' % (len(self.test_jobs)))
        if self.unchanged_tests:
            console.info('Skip %d unchanged tests when doing incremental test.' %
                         len(self.unchanged_tests))
            console.info('You can specify --full-test to run all tests.')

        run_tests = len(passed_run_results) + len(failed_run_results)

        total = len(self.test_jobs) + len(self.unrepaired_tests) + len(self.unchanged_tests)
        msg = ['Total %d tests' % total]
        if self.test_jobs:
            msg.append('%d scheduled' % len(self.test_jobs))
        if self.unchanged_tests:
            msg.append('%d unchanged' % len(self.unchanged_tests))
        if passed_run_results:
            msg.append('%d passed' % len(passed_run_results))
        if failed_run_results:
            msg.append('%d failed' % len(failed_run_results))
        cancelled_tests = len(self.test_jobs) - run_tests
        if cancelled_tests:
            msg.append('%d cancelled' % cancelled_tests)
        if self.unrepaired_tests:
            msg.append('%d unrepaired' % len(self.unrepaired_tests))
        console.notice(', '.join(msg) + '.')

        msg = []
        if self.repaired_tests:
            msg.append('%d repaired' % len(self.repaired_tests))
        if self.new_failed_tests:
            msg.append('%d new failed' % len(self.new_failed_tests))
        if msg:
            console.notice('Trend: ' + ', '.join(msg) + '.')
        if self._is_full_success(passed_run_results):
            console.notice('All %d tests passed!' % total)

    def _show_tests_result(self, passed_run_results, failed_run_results):
        """Show test details and summary according to the options."""
        if self.options.show_details:
            self._show_banner('Testing Details')
            self._show_tests_list(self.unchanged_tests, 'unchanged')
            if passed_run_results:
                console.info('Passed tests:')
                self._show_run_results(passed_run_results)
        if self.options.show_tests_slower_than is not None:
            self._show_slow_tests(passed_run_results, failed_run_results)
        if failed_run_results:  # Always show details of failed tests
            console.error('Failed tests:')
            self._show_run_results(failed_run_results, is_error=True)
        self._show_tests_list(self.repaired_tests, 'repaired')
        self._show_tests_list(self.new_failed_tests, 'new failed', 'error')
        self._show_unrepaired_results()

        self._show_tests_summary(passed_run_results, failed_run_results)

    def run(self):
        """Run all the test target programs."""
        self._collect_test_jobs()
        tests_run_list = []
        for target_key in self.test_jobs:
            target = self.target_database[target_key]
            test_env = self._prepare_env(target)
            cmd = [os.path.abspath(self._executable(target))]
            cmd += self.options.args
            if console.color_enabled():
                test_env['GTEST_COLOR'] = 'yes'
            else:
                test_env['GTEST_COLOR'] = 'no'
            test_env['GTEST_OUTPUT'] = 'xml'
            test_env['HEAPCHECK'] = target.attr.get('heap_check', '')
            pprof_path = config.get_item('cc_test_config', 'pprof_path')
            if pprof_path:
                test_env['PPROF_PATH'] = os.path.abspath(pprof_path)
            if self.options.coverage:
                test_env['BLADE_COVERAGE'] = 'true'
            tests_run_list.append((target, self._runfiles_dir(target), test_env, cmd))

        console.notice('%d tests to run' % len(tests_run_list))
        console.flush()
        scheduler = TestScheduler(tests_run_list, self.__test_jobs_num)
        try:
            scheduler.schedule_jobs()
        except KeyboardInterrupt:
            console.clear_progress_bar()
            console.error('KeyboardInterrupt, all tests stopped')
            console.flush()

        passed_run_results, failed_run_results = scheduler.get_results()
        self._save_test_history(passed_run_results, failed_run_results)
        self._save_test_summary(passed_run_results, failed_run_results)
        self._show_tests_result(passed_run_results, failed_run_results)

        if self.options.coverage:
            self._clean_for_coverage()
            self._generate_coverage_report()

        return 0 if self._is_full_success(passed_run_results) else 1
