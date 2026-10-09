"""Command definitions shared by protocols and environments."""

from typing import ClassVar

type CommandId = str


class BaseCommand:
    command_id: ClassVar[CommandId]
