"""Subscription interfaces provided by a connection."""

from typing import Protocol

from gradys_core.event import BaseEvent, EventHandler


class Subscription(Protocol):
    """
    Represents a subscription to an event type in an environment.
    """

    def unsubscribe(self) -> None:
        """Unregister the subscription from the environment."""
        ...


class Subscriber(Protocol):
    """
    Subscription capabilities provided by a connection to an environment.
    """

    def subscribe[E: BaseEvent](self, event: type[E], handler: EventHandler[E]) -> Subscription:
        ...
