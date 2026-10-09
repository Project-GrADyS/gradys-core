"""Validate protocol requirements against an environment's capabilities."""

from gradys_core.command import BaseCommand
from gradys_core.environment import Environment
from gradys_core.errors import ProtocolSetUpException
from gradys_core.event import BaseEvent


def validate_command_type(environment: Environment, command_type: type[BaseCommand]) -> None:
    """
    Validates that the environment supports sending commands of the specified type. If the protocol is not yet
    injected, the command type is buffered and will be checked once the protocol is injected.
    :param environment: The environment whose command capabilities are checked.
    :param command_type: The type of command to validate.
    """
    if not environment.command_checker(command_type):
        raise ProtocolSetUpException(f"Environment does not support sending commands of type "
                                     f"{command_type.__name__}.")

def validate_event_type(environment: Environment, event_type: type[BaseEvent]) -> None:
    """
    Validates that the environment supports subscribing to events of the specified type. If the protocol is not yet
    injected, the event type is buffered and will be checked once the protocol is injected.
    :param environment: The environment whose event capabilities are checked.
    :param event_type: The type of event to validate.
    """
    if not environment.event_checker(event_type):
        raise ProtocolSetUpException(f"Environment does not support subscribing to events of type "
                                     f"{event_type.__name__}.")
