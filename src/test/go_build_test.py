# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>

"""Integration tests for the modules-only Go rules (#1405 foundation).

Each test stands up a throwaway Go-module workspace and drives the real `blade`
binary, exercising:
  * go_binary built in file mode from its srcs;
  * multiple `main` files in one directory built as separate go_binary targets
    (impossible under package-mode building);
  * go_library compile-check (stamp) consumed by a go_binary that imports it;
  * per-target module discovery when the go.mod lives in a subdirectory.

Skipped when the go toolchain is unavailable.
"""

import glob
import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest


@unittest.skipUnless(shutil.which('go'), 'go toolchain not available')
class GoBuildTestBase(unittest.TestCase):
    def setUp(self):
        self.cur_dir = os.getcwd()
        here = os.path.dirname(os.path.abspath(__file__))
        self.blade = os.path.join(here, '..', '..', 'blade')
        self.work = tempfile.mkdtemp(prefix='blade_go_build_')
        go = shutil.which('go')
        self._write('BLADE_ROOT',
                    "go_config(go='%s', go_home='%s')\n"
                    % (go, os.path.join(self.work, 'gopath')))

    def tearDown(self):
        os.chdir(self.cur_dir)
        shutil.rmtree(self.work, ignore_errors=True)

    def _write(self, rel, text):
        path = os.path.join(self.work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def _blade(self, *args):
        os.chdir(self.work)
        return subprocess.run(
            [self.blade, *args],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')

    def _built(self, rel):
        """A file rel-path under any build_* dir, or None."""
        hits = glob.glob(os.path.join(self.work, 'build*', rel))
        return hits[0] if hits else None


class TestGoBinary(GoBuildTestBase):
    def testFileModeBinaryBuildsAndRuns(self):
        self._write('go.mod', 'module app\n\ngo 1.20\n')
        self._write('hello/hello.go', textwrap.dedent('''\
            package main
            import "fmt"
            func main() { fmt.Println("hello-blade-go") }
            '''))
        self._write('hello/BUILD', "go_binary(name='hello', srcs=['hello.go'])\n")
        p = self._blade('build', 'hello:hello')
        self.assertEqual(p.returncode, 0, p.stdout)
        binpath = self._built('hello/hello')
        self.assertIsNotNone(binpath, 'binary not built:\n%s' % p.stdout)
        out = subprocess.run([binpath], stdout=subprocess.PIPE, encoding='utf-8')
        self.assertEqual(out.stdout.strip(), 'hello-blade-go')

    def testMultipleMainsInOneDir(self):
        # Two files, each `package main` with its own main() -- one go_binary
        # each. Package-mode building would fail ("multiple definitions of
        # main"); file-mode builds each independently.
        self._write('go.mod', 'module tools\n\ngo 1.20\n')
        self._write('cmd/foo.go', textwrap.dedent('''\
            package main
            import "fmt"
            func main() { fmt.Println("foo") }
            '''))
        self._write('cmd/bar.go', textwrap.dedent('''\
            package main
            import "fmt"
            func main() { fmt.Println("bar") }
            '''))
        self._write('cmd/BUILD', textwrap.dedent('''\
            go_binary(name='foo', srcs=['foo.go'])
            go_binary(name='bar', srcs=['bar.go'])
            '''))
        p = self._blade('build', 'cmd:foo', 'cmd:bar')
        self.assertEqual(p.returncode, 0, p.stdout)
        for name, want in (('foo', 'foo'), ('bar', 'bar')):
            path = self._built('cmd/%s' % name)
            self.assertIsNotNone(path, 'binary %s not built:\n%s' % (name, p.stdout))
            out = subprocess.run([path], stdout=subprocess.PIPE, encoding='utf-8')
            self.assertEqual(out.stdout.strip(), want)


class TestGoLibrary(GoBuildTestBase):
    def testLibraryStampAndBinaryDependency(self):
        self._write('go.mod', 'module example\n\ngo 1.20\n')
        self._write('calc/calc.go', textwrap.dedent('''\
            package calc
            func Add(a, b int) int { return a + b }
            '''))
        self._write('calc/BUILD',
                    "go_library(name='calc', srcs=['calc.go'], visibility=['PUBLIC'])\n")
        self._write('app/main.go', textwrap.dedent('''\
            package main
            import (
                "fmt"
                "example/calc"
            )
            func main() { fmt.Println(calc.Add(2, 3)) }
            '''))
        self._write('app/BUILD',
                    "go_binary(name='app', srcs=['main.go'], deps=['//calc:calc'])\n")
        p = self._blade('build', 'app:app')
        self.assertEqual(p.returncode, 0, p.stdout)
        # go_library produced its compile-check stamp...
        self.assertIsNotNone(self._built('calc/calc'),
                             'go_library stamp missing:\n%s' % p.stdout)
        # ...and the binary that imports it built and runs.
        binpath = self._built('app/app')
        self.assertIsNotNone(binpath, 'binary not built:\n%s' % p.stdout)
        out = subprocess.run([binpath], stdout=subprocess.PIPE, encoding='utf-8')
        self.assertEqual(out.stdout.strip(), '5')


class TestSubdirModule(GoBuildTestBase):
    def testModuleInSubdirectory(self):
        # go.mod lives in svc/, not the workspace root: the target must be built
        # in the svc module (via `go -C svc`).
        self._write('svc/go.mod', 'module svc\n\ngo 1.20\n')
        self._write('svc/main.go', textwrap.dedent('''\
            package main
            import "fmt"
            func main() { fmt.Println("in-subdir-module") }
            '''))
        self._write('svc/BUILD', "go_binary(name='svc', srcs=['main.go'])\n")
        p = self._blade('build', 'svc:svc')
        self.assertEqual(p.returncode, 0, p.stdout)
        binpath = self._built('svc/svc')
        self.assertIsNotNone(binpath, 'binary not built:\n%s' % p.stdout)
        out = subprocess.run([binpath], stdout=subprocess.PIPE, encoding='utf-8')
        self.assertEqual(out.stdout.strip(), 'in-subdir-module')


@unittest.skipUnless(shutil.which('go') and shutil.which('cc'),
                     'go or cc toolchain not available')
class TestCgo(GoBuildTestBase):
    def testGoBinaryLinksCcLibrary(self):
        # A go_binary with `import "C"` links a Blade cc_library: Blade feeds the
        # library's include dir (CGO_CFLAGS) and static archive (CGO_LDFLAGS) to
        # `go build`, and orders the archive ahead of the go link.
        self._write('go.mod', 'module cgoapp\n\ngo 1.20\n')
        self._write('greeter/greeter.h', textwrap.dedent('''\
            #ifndef GREETER_H
            #define GREETER_H
            const char* greet(void);
            #endif
            '''))
        self._write('greeter/greeter.c', textwrap.dedent('''\
            #include "greeter/greeter.h"
            const char* greet(void) { return "hi-from-cc"; }
            '''))
        self._write('greeter/BUILD',
                    "cc_library(name='greeter', srcs=['greeter.c'], "
                    "hdrs=['greeter.h'], visibility=['PUBLIC'])\n")
        self._write('app/main.go', textwrap.dedent('''\
            package main

            /*
            #include "greeter/greeter.h"
            */
            import "C"
            import "fmt"

            func main() { fmt.Println(C.GoString(C.greet())) }
            '''))
        self._write('app/BUILD',
                    "go_binary(name='app', srcs='main.go', deps=['//greeter:greeter'])\n")
        p = self._blade('build', 'app:app')
        self.assertEqual(p.returncode, 0, p.stdout)
        binpath = self._built('app/app')
        self.assertIsNotNone(binpath, 'cgo binary not built:\n%s' % p.stdout)
        out = subprocess.run([binpath], stdout=subprocess.PIPE, encoding='utf-8')
        self.assertEqual(out.stdout.strip(), 'hi-from-cc')

    def testCgoCollectsTransitiveCcArchive(self):
        # greeter -> base: the go binary must link *both* archives (rooted at the
        # direct cc dep, walking its transitive closure), not just the direct one.
        self._write('go.mod', 'module cgotrans\n\ngo 1.20\n')
        self._write('base/base.h', 'const char* base_word(void);\n')
        self._write('base/base.c',
                    '#include "base/base.h"\n'
                    'const char* base_word(void) { return "hi-from-base"; }\n')
        self._write('base/BUILD',
                    "cc_library(name='base', srcs=['base.c'], hdrs=['base.h'], "
                    "visibility=['PUBLIC'])\n")
        self._write('greeter/greeter.h', 'const char* greet(void);\n')
        self._write('greeter/greeter.c',
                    '#include "greeter/greeter.h"\n'
                    '#include "base/base.h"\n'
                    'const char* greet(void) { return base_word(); }\n')
        self._write('greeter/BUILD',
                    "cc_library(name='greeter', srcs=['greeter.c'], "
                    "hdrs=['greeter.h'], deps=['//base:base'], visibility=['PUBLIC'])\n")
        self._write('app/main.go', textwrap.dedent('''\
            package main

            /*
            #include "greeter/greeter.h"
            */
            import "C"
            import "fmt"

            func main() { fmt.Println(C.GoString(C.greet())) }
            '''))
        self._write('app/BUILD',
                    "go_binary(name='app', srcs='main.go', deps=['//greeter:greeter'])\n")
        p = self._blade('build', 'app:app')
        self.assertEqual(p.returncode, 0, p.stdout)
        binpath = self._built('app/app')
        self.assertIsNotNone(binpath, 'cgo binary not built:\n%s' % p.stdout)
        out = subprocess.run([binpath], stdout=subprocess.PIPE, encoding='utf-8')
        # Resolves a symbol that lives in the *transitive* archive.
        self.assertEqual(out.stdout.strip(), 'hi-from-base')


class TestGoUnconfigured(unittest.TestCase):
    """A go target with `go` unconfigured must fail with a clear analyze-stage
    message, not a cryptic `ninja: unknown build rule 'gobinary'`. Needs no go
    toolchain -- it exercises exactly the unconfigured path."""

    def setUp(self):
        self.cur_dir = os.getcwd()
        here = os.path.dirname(os.path.abspath(__file__))
        self.blade = os.path.join(here, '..', '..', 'blade')
        self.work = tempfile.mkdtemp(prefix='blade_go_noconf_')
        self._write('BLADE_ROOT', "go_config(go='')\n")  # unconfigured
        self._write('go.mod', 'module x\n\ngo 1.20\n')
        self._write('app/main.go', 'package main\nfunc main() {}\n')
        self._write('app/BUILD', "go_binary(name='app', srcs='main.go')\n")

    def tearDown(self):
        os.chdir(self.cur_dir)
        shutil.rmtree(self.work, ignore_errors=True)

    def _write(self, rel, text):
        path = os.path.join(self.work, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(text)

    def testClearErrorWhenGoUnconfigured(self):
        os.chdir(self.work)
        p = subprocess.run(
            [self.blade, 'build', 'app:app'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8')
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('Go toolchain is not configured', p.stdout)
        self.assertNotIn('unknown build rule', p.stdout)  # not the cryptic one


if __name__ == '__main__':
    unittest.main()
