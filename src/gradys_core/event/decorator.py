from dataclasses import dataclass

from gradys_core.event import BaseEvent
from .error_messages import invalid_event_type, invalid_event_base_class


def environment_event(event_class: type[BaseEvent]):
    """
    Decorator to mark a class as an environment event. All environment events must be decorated with this decorator
    to be recognized as valid events in the simulation environment. Only classes that inherit from BaseEvent can be
    decorated with this decorator.

    This decorator marks the class as a dataclass with slots and frozen attributes.

    :exception TypeError: if the event class does not inherit from BaseEvent.
    """

    if not issubclass(event_class, BaseEvent):
        raise TypeError(invalid_event_base_class(event_class.__name__, BaseEvent.__name__))

    dataclass_decorator = dataclass(slots=True, frozen=True)

    setattr(event_class, "__is_environment_event__", True)

    return dataclass_decorator(event_class)

def is_environment_event(event: type[BaseEvent]) -> bool:
    """
    Check if the given event class is marked as an environment event.
    """
    return getattr(event, "__is_environment_event__", False)

def validate_environment_event(event: type[BaseEvent]) -> None:
    """
    Validate that the given event class is marked as an environment event.

    :exception TypeError: if the event class is not a valid environment event.
    """
    if not is_environment_event(event):
        raise TypeError(invalid_event_type(event.__name__, environment_event.__name__))
