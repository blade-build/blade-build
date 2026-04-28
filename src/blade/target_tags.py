# Copyright (c) 2021 Tencent Inc.
# All rights reserved.
#
# Author: CHEN Feng <chen3feng@gmail.com>
# Date:   Feb 28, 2021

"""
Build target tag validator and filter.
"""

import re


_TAG_RE = re.compile(r'\w+:\w+$')


def is_valid(tag):
    """Is a valid tag name"""
    return _TAG_RE.match(tag)


_TOKEN_RE = re.compile(r'(\(|\)|\bnot\b|\band\b|\bor\b|(?P<tags>\b\w+:\w+(,\w+)*\b)|\s+)')


def _token_iter(expr):
    pos = 0
    remain = expr
    while remain:
        pos = len(expr) - len(remain)
        m = _TOKEN_RE.match(remain)
        if not m:
            yield pos, None
            return
        token = m.group(0)
        remain = remain[len(token):]
        yield pos, token


def _convert_expression(expr, func_name):
    """Convert a filter expression into a python expression."""
    tokens = []
    stack = []

    for pos, token in _token_iter(expr):
        if token is None:
            error = 'Invalid expression: "%s"' % expr[pos:]
            return None, error
        if token.isspace():
            continue
        if token == '(':
            tokens.append(token)
            stack.append(('(', pos))
        elif token == ')':
            if stack:
                tokens.append(token)
                stack.pop()
            else:
                error = 'Unbalanced ")": "%s"' % (expr[pos:])
                return None, error
        elif token in ('not', 'and', 'or'):
            tokens.append(' %s ' % token)
        else:
            scope, names = token.split(':')
            names = names.split(',')
            args = ', '.join(['"{}:{}"'.format(scope, name) for name in names])
            tokens.append('{}({})'.format(func_name, args))
    if stack:
        error = 'Unbalanced "(": "%s"' % expr[stack[-1][1]:]
        return None, error
    return ''.join(tokens), None


def _compile_filter_expr(expr, match_func):
    """Compile a filter expression into byte code."""
    result, error = _convert_expression(expr, match_func)
    if not result:
        return result, error
    try:
        code = compile(result, '--tags-filter', 'eval')
    except SyntaxError as e:
        return None, "{}: {}".format(str(e), result)
    return code, error


def compile_filter(expr):
    """Compile a filter expression into a filter function."""
    def filter_function(target):
        match_tags = target.match_tags
        return eval(filter_function.code)  # pylint: disable=eval-used
    code, error = _compile_filter_expr(expr, 'match_tags')
    if not code:
        return None, error
    filter_function.code = code
    return filter_function, []


if __name__ == '__main__':
    import sys
    print(_convert_expression(sys.argv[1], 'check'))
