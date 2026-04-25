#!/bin/bash

# Copyright (c) 2011 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>
# Created:   Feb 22, 2013
#
# Script to setup, run and cleanup testing.

if [ $# -lt 1 ]; then
    echo "Usage: $1 <test_file_name>" >&2
    exit 1
fi

cd `dirname $0`

ROOT="$(cd ../.. && pwd)"

rm -f $ROOT/.coverage*

cat > $ROOT/.coveragerc << EOF
[run]
data_file = $ROOT/.coverage
omit =
    */src/blade/pathlib.py
    */src/blade/version.py

parallel = true
EOF

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
else
    PYTHON=python
fi

export PYTHONPATH=$PYTHONPATH:$ROOT/src
export BLADE_PYTHON_INTERPRETER="$PYTHON -m coverage run --source=$ROOT/src/blade --rcfile=$ROOT/.coveragerc"

$PYTHON -B "$@"
exit_code=$?

$PYTHON -m coverage combine --rcfile=$ROOT/.coveragerc
$PYTHON -m coverage report --rcfile=$ROOT/.coveragerc

exit $exit_code
