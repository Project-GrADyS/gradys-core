from typing import Callable

from gradys_core.command import BaseCommand
from gradys_core.errors import ProtocolSetUpException
from gradys_core.event import BaseEvent

type CommandCapabilityChecker = Callable[[type[BaseCommand]], bool]
type EventCapabilityChecker = Callable[[type[BaseEvent]], bool]


def validate_command_type(checker: CommandCapabilityChecker, command_type: type[BaseCommand]) -> None:
    """
    Validates that the environment supports sending commands of the specified type. If the protocol is not yet
    injected, the command type is buffered and will be checked once the protocol is injected.
    :param checker: A callable that checks if the environment supports sending commands of a specific type.
    :param command_type: The type of command to validate.
    """
    if not checker(command_type):
        raise ProtocolSetUpException(f"Environment does not support sending commands of type "
                                     f"{command_type.__name__}.")

def validate_event_type(checker: EventCapabilityChecker, event_type: type[BaseEvent]) -> None:
    """
    Validates that the environment supports subscribing to events of the specified type. If the protocol is not yet
    injected, the event type is buffered and will be checked once the protocol is injected.
    :param checker: A callable that checks if the environment supports subscribing to events of a specific type.
    :param event_type: The type of event to validate.
    """
    if not checker(event_type):
        raise ProtocolSetUpException(f"Environment does not support subscribing to events of type "
                                     f"{event_type.__name__}.")