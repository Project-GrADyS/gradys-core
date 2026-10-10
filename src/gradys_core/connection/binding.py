"""Validate protocol requirements against an environment's capabilities."""

from gradys_core.environment import Environment
from gradys_core.errors import ProtocolSetUpException
from gradys_core.primitives import BaseCommand, BaseEvent


def validate_command_type(environment: Environment, command_type: type[BaseCommand]) -> None:
    """Check a command requirement against an environment.

    Args:
        environment: Adapter whose command support is queried.
        command_type: Command class the protocol needs to send.

    Raises:
        ProtocolSetUpException: If the environment rejects the command type.
    """
    if not environment.command_checker(command_type):
        raise ProtocolSetUpException(f"Environment does not support sending commands of type "
                                     f"{command_type.__name__}.")

def validate_event_type(environment: Environment, event_type: type[BaseEvent]) -> None:
    """Check an event requirement against an environment.

    Args:
        environment: Adapter whose event support is queried.
        event_type: Event class the protocol needs to receive.

    Raises:
        ProtocolSetUpException: If the environment rejects the event type.
    """
    if not environment.event_checker(event_type):
        raise ProtocolSetUpException(f"Environment does not support subscribing to events of type "
                                     f"{event_type.__name__}.")
