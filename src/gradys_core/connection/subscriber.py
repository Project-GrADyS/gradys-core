"""Subscription interfaces provided by a connection."""

from dataclasses import dataclass
from typing import Optional, Protocol

from gradys_core.primitives import BaseEvent, EventHandler


class Subscription(Protocol):
    """
    Represents a subscription to an event type in an environment.
    """

    def unsubscribe(self) -> None:
        """Unregister the subscription from the environment."""
        ...

@dataclass(frozen=True, slots=True)
class SubscriptionOptions:
    """Options for a subscription to an event type in an environment."""

    once: bool = False
    """If True, the subscription will be automatically unsubscribed after the first event is received."""


class Subscriber(Protocol):
    """
    Subscription capabilities provided by a connection to an environment.
    """

    def subscribe[E: BaseEvent](self, 
                                event: type[E], 
                                handler: EventHandler[E], 
                                options: Optional[SubscriptionOptions] = None) -> Subscription:
        ...
