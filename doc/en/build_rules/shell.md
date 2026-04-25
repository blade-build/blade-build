# Shell Test Rule

Run shell script based tests. you can run multiple processes in the script, it is useful for writing complex tests.

```python
sh_test(
    name = 'integration_test',
    srcs = 'integration_test.sh',
    testdata = [
        ('$(location //rpc/test:test_stub_server)', 'test_stub_server'),
        ('$(location //rpc/test:test_client)', 'test_client'),
    ],
)
```

All of the file in the `testdata` can be accessed in the test script, it should use exit code to report the test result.
