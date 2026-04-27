#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Unit tests for blade.builtin_tools pybinary bootstrap generation.

"""Pin the shell bootstrap that blade prepends to every py_binary / py_test.

The bootstrap is a `#!/bin/sh` script that lives at the head of the final
zip-appended executable. It must:

1. Invoke an interpreter that actually exists on the host. Modern systems
   (macOS, recent Debian/Ubuntu) ship only ``python3``; a hardcoded
   ``python`` invocation fails with ``exec: python: not found`` at test
   time — a silent, runtime-only regression.
2. Respect ``$BLADE_PYTHON_INTERPRETER`` so users whose default python3
   is older than 3.10 (or who need a specific virtualenv) can override
   just the downstream py_binary execution the same way they already
   override blade's own launcher (see ``blade._check_python``).
3. Forward ``"$@"`` to the module so test args / binary flags reach the
   user's code intact.

The test writes the bootstrap-carrying pybin to a real file and reads it
back as text — byte-for-byte. That's deliberate: the bootstrap is what
``/bin/sh`` is going to parse at runtime, so there is no safer unit than
the exact bytes on disk.
"""

import os
import stat
import sys
import tempfile
import unittest

# Make ``import blade.*`` resolve against the in-tree sources without
# requiring blade to be installed.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, os.path.join(_REPO_ROOT, 'src'))

from blade import builtin_tools  # noqa: E402  (sys.path tweak above)


def _make_minimal_pylib(pylib_path, src_path, base_dir):
    """Write a minimal .pylib descriptor pointing at *src_path*.

    A .pylib is not a zip — it is a Python literal (consumed via ``eval``
    by ``_pybin_add_pylib``) of the form::

        {'base_dir': '<relative base>', 'srcs': [(src_abs, md5), ...]}

    For bootstrap-generation tests we do not care what's inside the
    source; we only need ``generate_python_binary`` to stream through
    without crashing so that the bootstrap bytes get prepended.
    """
    payload = {
        'base_dir': base_dir,
        'srcs': [(src_path, '0' * 32)],
    }
    with open(pylib_path, 'w', encoding='utf-8') as f:
        f.write(repr(payload))


class GeneratePythonBinaryBootstrapTest(unittest.TestCase):
    """Pin the shell header that wraps every py_binary / py_test."""

    def _build_pybin(self, mainentry, tmpdir):
        # The source file has to actually exist — _pybin_add_pylib uses
        # pybin_zip.write(libsrc, arcname) to copy it in.
        src = os.path.join(tmpdir, 'app', 'main.py')
        os.makedirs(os.path.dirname(src), exist_ok=True)
        with open(src, 'w', encoding='utf-8') as f:
            f.write('def run():\n    pass\n')

        pylib = os.path.join(tmpdir, 'app.pylib')
        _make_minimal_pylib(pylib, src_path=src, base_dir=tmpdir)

        # Use a name that does not collide with the ``app/`` source dir.
        pybin = os.path.join(tmpdir, 'bin')
        # generate_python_binary signature:
        #   (pybin, basedir, exclusions_csv, mainentry, args)
        # where args is the list of .pylib / .egg / .whl inputs.
        builtin_tools.generate_python_binary(
            pybin, '', '', mainentry, [pylib])
        return pybin

    def _read_bootstrap(self, pybin):
        """Return the #!/bin/sh header (everything before the zip magic)."""
        with open(pybin, 'rb') as f:
            blob = f.read()
        # The zip segment starts at the first PK\x03\x04 local-file header.
        zip_start = blob.find(b'PK\x03\x04')
        self.assertNotEqual(
            zip_start, -1, 'expected a zip segment after the sh bootstrap')
        return blob[:zip_start].decode('utf-8')

    def test_bootstrap_uses_python3_not_bare_python(self):
        """Regression pin: hardcoding ``python`` breaks on macOS & modern Debian.

        The old bootstrap read ``exec python -m "..."`` and failed at
        runtime on any host where only ``python3`` is on PATH. The fix is
        to default to ``python3``; this test guards the default so a
        well-meaning refactor cannot silently reintroduce the bug.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            pybin = self._build_pybin('app.main', tmpdir)
            bootstrap = self._read_bootstrap(pybin)
        self.assertIn('python3', bootstrap)
        # The exact token ``exec python `` (with a trailing space) is what
        # /bin/sh would resolve against PATH; make sure the naked form is
        # not present.
        self.assertNotIn('exec python ', bootstrap)
        self.assertNotIn('exec python\t', bootstrap)

    def test_bootstrap_honours_blade_python_interpreter(self):
        """Users can pin a specific interpreter without patching blade.

        Mirrors the escape hatch the top-level ``blade`` launcher already
        offers via ``BLADE_PYTHON_INTERPRETER`` when the host default
        python3 is too old.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            pybin = self._build_pybin('app.main', tmpdir)
            bootstrap = self._read_bootstrap(pybin)
        # The indirection syntax must be ${VAR:-default}, not $VAR (which
        # would break when the env var is unset) nor ${VAR-default}
        # (which would keep an accidental empty string).
        self.assertIn('${BLADE_PYTHON_INTERPRETER:-python3}', bootstrap)

    def test_bootstrap_preserves_mainentry_and_forwards_argv(self):
        """Entry point and ``"$@"`` must survive the fix verbatim."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pybin = self._build_pybin('suites.py_basic.greeter_test', tmpdir)
            bootstrap = self._read_bootstrap(pybin)
        self.assertIn('-m "suites.py_basic.greeter_test"', bootstrap)
        self.assertIn('"$@"', bootstrap)
        # PYTHONPATH prepend is what lets the zip-embedded modules import.
        self.assertIn('PYTHONPATH="$0:$PYTHONPATH"', bootstrap)

    def test_bootstrap_starts_with_posix_shebang(self):
        """The bootstrap is parsed by /bin/sh, not bash. Pin the shebang."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pybin = self._build_pybin('app.main', tmpdir)
            with open(pybin, 'rb') as f:
                head = f.read(16)
        self.assertTrue(
            head.startswith(b'#!/bin/sh\n'),
            'unexpected shebang bytes: %r' % head)

    def test_generated_pybin_is_executable(self):
        """Blade marks the generated file 0755; regression-pin it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pybin = self._build_pybin('app.main', tmpdir)
            mode = stat.S_IMODE(os.stat(pybin).st_mode)
        self.assertTrue(mode & stat.S_IXUSR, 'owner exec bit missing: %o' % mode)
        self.assertTrue(mode & stat.S_IXGRP, 'group exec bit missing: %o' % mode)
        self.assertTrue(mode & stat.S_IXOTH, 'other exec bit missing: %o' % mode)


if __name__ == '__main__':
    unittest.main()
