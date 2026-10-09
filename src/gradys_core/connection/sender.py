"""Command sending interface provided by a connection."""

from typing import Protocol

from gradys_core.primitives import BaseCommand


class Sender(Protocol):
    """Command sending capabilities provided by a connection to an environment."""

    def send(self, command: BaseCommand) -> None:
        ...
