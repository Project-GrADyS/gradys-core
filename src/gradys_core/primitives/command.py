"""Command definitions shared by protocols and environments."""

from typing import ClassVar

type CommandId = str
"""String identifier used by environment adapters to identify a command kind."""


class BaseCommand:
    """Base for requests that a protocol sends to an execution environment.

    Subclasses define a ``command_id`` and any payload they need. This base does
    not generate a constructor or enforce payload immutability; a frozen
    dataclass is one way to define a concrete command. Execution and capability
    matching are supplied by the environment.
    """

    command_id: ClassVar[CommandId]
    """Identifier for the command kind, shared by all instances of its class."""
