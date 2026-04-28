"""
Constants.
"""

# See http://google-perftools.googlecode.com/svn/trunk/doc/heap_checker.html
HEAP_CHECK_VALUES = {
    '',
    'minimal',
    'normal',
    'strict',
    'draconian',
    'as-is',
    'local',
}

SEVERITIES = {'debug', 'info', 'notice', 'warning', 'error'}

ALL_COMMAND_TARGETS = '__all_command_targets__'


class HELP:
    build_jobs = 'Specifies the number of build jobs (commands) to run simultaneously'
    test_jobs = 'The number of tests to run simultaneously'
    run_unrepaired_tests = 'Whether run unrepaired(no changw after previous failure) tests during incremental test'
    jar_compression_level = 'Jar compress level. Due to the limitation of the jar command, only 0 (no compression) or empty (default) are allowed'
    fat_jar_compression_level = 'Fat jar compress level, must between 0 (store only) and 9 (max but slow)'
    maven_download_concurrency = 'Number of processes to pre-download maven_jar, 0 to disable pre-downloading'
