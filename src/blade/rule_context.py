# Copyright (c) 2026 Tencent Inc.
# All rights reserved.

"""
``RuleContext`` — the narrow interface a rule provider sees.

Rule providers (see ``rule_registry.py``) need the toolchain, config, options
and a way to emit rules, but should not depend on the whole
``_NinjaFileHeaderGenerator`` god object. ``RuleContext`` wraps that generator
and exposes a small, stable surface.

This is intentionally a seam, not yet a reduction: in M1 the built-in providers
still delegate to the generator's existing ``generate_*_rules`` methods via
``ctx.generator``, and ``build.ninja`` stays byte-identical. As rule groups are
migrated to construct ``NinjaRule`` values directly (M2), they depend only on
this interface, so the generator's helper bodies can later move out from under
them with no provider changes.
"""

from blade import config
from blade.ninja_rule import NinjaRule


class RuleContext:
    """Context passed to each rule provider at generation time."""

    def __init__(self, generator):
        # The underlying _NinjaFileHeaderGenerator. Escape hatch used by M1
        # built-in providers that still call its generate_*_rules methods.
        self.generator = generator
        self.options = generator.options
        self.build_dir = generator.build_dir
        self.blade_path = generator.blade_path
        self.toolchain = generator.build_toolchain
        self.accelerator = generator.build_accelerator

    def config_section(self, name):
        return config.get_section(name)

    def builtin_command(self, builder, args=''):
        """Build the command line that runs a blade builtin tool.

        Forwards to the generator's `_builtin_command`, which handles the
        per-platform PYTHONPATH / interpreter wrapping.
        """
        return self.generator._builtin_command(builder, args)

    def add_line(self, line):
        """Emit one raw line into the ninja header buffer."""
        self.generator._add_line(line)

    def emit_rule(self, rule: NinjaRule):
        """Emit a NinjaRule into the ninja header buffer."""
        self.generator._record_rule_name(rule.name)
        for line in rule.emit():
            self.generator._add_line(line)
