# Copyright (c) 2026 The Blade Authors.
# All rights reserved.

"""
A registry of ninja-rule **providers**.

Historically the set of ninja ``rule`` blocks was produced by a hardcoded,
ordered method list in ``_NinjaFileHeaderGenerator.generate`` (backend.py).
That coupled the backend to every language: a new rule could not be contributed
without editing that list. This registry inverts the dependency — each rule
group registers a provider, and the backend becomes a thin loop over the
registered providers in a deterministic order.

A provider is a callable ``provider(ctx: RuleContext) -> None`` that emits its
rules into ``ctx`` (see ``rule_context.py``). Providers are ordered by an
explicit integer ``order`` (NOT import or registration order, which are
fragile); ties break by name for stability. Spaced ``ORDER_*`` constants below
reproduce the original ``generate()`` sequence and leave room to slot new
providers between existing ones.
"""


# Explicit order keys reproducing the original generate() sequence.
# Spaced by 10 so new providers (including future custom rules) can slot
# between without renumbering.
ORDER_COMMON = 0
ORDER_CC = 10
ORDER_PROTO = 20
ORDER_RESOURCE = 30
ORDER_JAVA_SCALA = 40
ORDER_THRIFT = 50
ORDER_PYTHON = 60
ORDER_GO = 70
ORDER_SHELL = 80
ORDER_LEX_YACC = 90
ORDER_PACKAGE = 100
ORDER_VERSION = 110
ORDER_CUDA = 120
ORDER_CUSTOM = 1000  # user-defined rules (#829) slot after the built-ins


# name -> (order, provider). Keyed by name so registration is idempotent
# (re-registering the same name replaces it), which keeps the registry stable
# across module re-imports in tests.
_providers: dict = {}


def register_rule_provider(provider, *, order, name=None):
    """Register a ninja-rule provider.

    Args:
        provider: callable ``provider(ctx) -> None`` that emits rules into the
            given RuleContext.
        order: explicit integer ordering key (use an ``ORDER_*`` constant).
        name: stable identifier; defaults to ``provider.__name__``. Re-using a
            name replaces the previous registration (idempotent).
    """
    key = name or getattr(provider, '__name__', repr(provider))
    _providers[key] = (order, provider)
    return provider


def rule_providers():
    """Return registered providers sorted by (order, name)."""
    return [provider for _name, (_order, provider)
            in sorted(_providers.items(), key=lambda kv: (kv[1][0], kv[0]))]
