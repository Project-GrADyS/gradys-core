"""Define and recognize events marked for use by environment adapters."""

from dataclasses import dataclass

from .error_messages import invalid_event_base_class, invalid_event_type
from .event import BaseEvent


def environment_event[E: BaseEvent](event_class: type[E]) -> type[E]:
    """Mark an event definition and convert it to a frozen dataclass with slots.

    Annotated instance fields become constructor arguments. The returned class
    preserves the event's static type.

    Args:
        event_class: A subclass of ``BaseEvent`` to decorate.

    Returns:
        The decorated event class, which replaces the original class.

    Raises:
        TypeError: If the class does not inherit from ``BaseEvent``, or its
            definition is incompatible with a frozen dataclass with slots.
    """
    if not issubclass(event_class, BaseEvent):
        raise TypeError(invalid_event_base_class(event_class.__name__, BaseEvent.__name__))

    dataclass_decorator = dataclass(slots=True, frozen=True)

    event_class.__is_environment_event__ = True

    return dataclass_decorator(event_class)

def is_environment_event(event: type[BaseEvent]) -> bool:
    """Return whether an event class carries the environment-event marker.

    The marker may be inherited. This does not check whether a particular
    environment supports the class or validate its payload.
    """
    return getattr(event, "__is_environment_event__", False)

def validate_environment_event(event: type[BaseEvent]) -> None:
    """Require the environment-event marker on an event class.

    Raises:
        TypeError: If the class is not marked as an environment event.
    """
    if not is_environment_event(event):
        raise TypeError(invalid_event_type(event.__name__, environment_event.__name__))
