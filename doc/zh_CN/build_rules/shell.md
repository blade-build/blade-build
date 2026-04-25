# Shell Test 规则

编写基于 shell 脚本的测试，在测试里可以起多个进程，可以用于集成测试等比较复杂的场合。

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

testdata 中描述的文件，可以在测试程序（integration_test.sh）里访问到。程序结束时用进程退出码来报告成功/失败。
