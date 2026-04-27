#!/bin/bash
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.
#
# Run every unit test under src/tests/unit/.
#
# Unit tests here are pure-Python (no subprocess, no real blade launcher,
# no testdata/). They mock out run_command and exercise logic in isolation,
# and thus run on any machine that has Python >= 3.10.
#
# The older integration tests in src/test/ are NOT driven by this script;
# use src/test/runall.sh for those.

set -eu

here=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$here/../.." && pwd)

if command -v python3 >/dev/null 2>&1; then
    PYTHON=${PYTHON:-python3}
else
    PYTHON=${PYTHON:-python}
fi

export PYTHONPATH="$repo_root/src${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON" -m unittest discover -s "$here" -p '*_test.py' -v
