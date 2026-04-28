#!/usr/bin/env python3
# Copyright (c) 2026 Tencent Inc.
# All rights reserved.

"""
Shared type aliases for the blade codebase.

Module name note: called ``blade_types`` (not ``types``) so that it never
shadows the stdlib ``types`` module in a reader's mental model or through
any accidental non-absolute import.

Design: external entry points (rule-entry functions such as `cc_library`,
`py_library`, `proto_library`, ...) accept BUILD-file-friendly unions, while
internal helpers and `Target` attributes use the normalized `list[str]`.

Layering
--------
1. **Outer (rule-entry level)** -- `src/blade/*_target.py` top-level public
   functions: parameters typed `StrOrList` / `StrOrListOpt` so that BUILD
   files may write either ``srcs='foo.cc'`` or ``srcs=['a.cc', 'b.cc']``.
   Rule bodies must normalize once via ``var_to_list`` /
   ``var_to_list_or_none`` right at the top.
2. **Middle (Target attributes / `Target.__init__`)**: normalized
   ``list[str]`` only; no ``str`` branches, no ``isinstance(x, str)``.
3. **Inner (helpers / util / backend)**: ``list[str]`` (or
   ``collections.abc.Sequence[str]`` for read-only iteration). Passing a
   bare ``str`` here is a bug; pyright will flag it.

`StrOrList` should therefore only appear in rule-entry function signatures.
"""

from __future__ import annotations

from typing import Optional, Union

# A BUILD-file-friendly string-or-list-of-strings union.
#
# Used in rule-entry parameter annotations (and nowhere else). Always
# normalize via ``var_to_list`` in the function body before forwarding.
StrOrList = Union[str, list[str]]

# Same as `StrOrList` but also allows None, for parameters that carry a
# "not configured" sentinel distinct from an empty list. Normalize via
# ``var_to_list_or_none``.
StrOrListOpt = Optional[StrOrList]

__all__ = ['StrOrList', 'StrOrListOpt']
