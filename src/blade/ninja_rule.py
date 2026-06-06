# Copyright (c) 2026 Tencent Inc.
# All rights reserved.

"""
The ``NinjaRule`` value type: a single ninja ``rule`` declaration.

This is the value half of the rule registry (see ``rule_registry.py``). It
holds the fields of a ninja ``rule`` block and knows how to render them.
``emit()`` reproduces, line for line, the text that
``_NinjaFileHeaderGenerator.generate_rule`` historically wrote, so moving rule
production onto this type keeps the generated ``build.ninja`` byte-identical.
"""

from dataclasses import dataclass

from blade import console


@dataclass(frozen=True)
class NinjaRule:
    """One ninja ``rule`` declaration.

    Field order in :meth:`emit` matches the historical ``generate_rule``
    emission order exactly (command, description, depfile, generator, pool,
    restat, rspfile, rspfile_content, deps, trailing blank line).
    """

    name: str
    command: str
    description: str | None = None
    depfile: str | None = None
    generator: bool = False
    pool: str | None = None
    restat: bool = False
    rspfile: str | None = None
    rspfile_content: str | None = None
    deps: str | None = None

    def emit(self) -> list[str]:
        """Render this rule as a list of lines (no trailing newlines).

        The caller appends each line with its own newline (matching the old
        ``_add_line`` behaviour). The final empty string is the blank line that
        separated rules for readability.
        """
        lines = [
            'rule %s' % self.name,
            '  command = %s' % self.command,
        ]
        if self.description:
            lines.append('  description = %s' % console.colored(self.description, 'dimpurple'))
        if self.depfile:
            lines.append('  depfile = %s' % self.depfile)
        if self.generator:
            lines.append('  generator = 1')
        if self.pool:
            lines.append('  pool = %s' % self.pool)
        if self.restat:
            lines.append('  restat = 1')
        if self.rspfile:
            lines.append('  rspfile = %s' % self.rspfile)
        if self.rspfile_content:
            lines.append('  rspfile_content = %s' % self.rspfile_content)
        if self.deps:
            lines.append('  deps = %s' % self.deps)
        lines.append('')  # An empty line to improve readability
        return lines
