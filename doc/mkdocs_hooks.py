"""MkDocs build hooks.

Rewrite repo-relative links to absolute GitHub URLs at build time, so the source
markdown stays unchanged. The docs link to repo files/dirs with paths like
`../../tool/x.sh` or `../../src/blade/x.py` -- correct when the markdown is viewed
on GitHub, but they 404 on the rendered doc site (those targets aren't part of
the docs). This hook converts them to absolute github.com URLs during the build.
"""
import re

_BASE = 'https://github.com/blade-build/blade-build'

# Markdown links pointing two levels up into the repo: `../../tool[/...]` or
# `../../src[/...]`. A trailing sub-path means a file (blob); a bare dir is a tree.
_LINK = re.compile(r'\(\.\./\.\./(tool|src)((?:/[^)]*)?)\)')


def _to_github_url(match):
    top, rest = match.group(1), match.group(2)
    kind = 'blob' if rest else 'tree'
    return f'({_BASE}/{kind}/master/{top}{rest})'


def on_page_markdown(markdown, **kwargs):
    return _LINK.sub(_to_github_url, markdown)
