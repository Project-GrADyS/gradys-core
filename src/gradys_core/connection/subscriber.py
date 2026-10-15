"""Subscription interfaces provided by a connection."""

from dataclasses import dataclass
from typing import Protocol

from gradys_core.primitives import BaseEvent, EventHandler


class Subscription(Protocol):
    """Control one event-handler registration."""

    def unsubscribe(self) -> None:
        """Remove this handler registration."""
        ...

@dataclass(frozen=True, slots=True)
class SubscriptionOptions:
    """Immutable delivery options for one event-handler registration.

    Attributes:
        once: Deliver at most one event to the handler and automatically
            unregister it. Defaults to false.
    """

    once: bool = False


class Subscriber(Protocol):
    """Subscription capabilities provided by a connection to an environment."""

    def subscribe[E: BaseEvent](self, 
                                event: type[E], 
                                handler: EventHandler[E], 
                                options: SubscriptionOptions | None = None) -> Subscription:
        """Register an event handler on the connected environment.

        Args:
            event: Event class to subscribe to.
            handler: Callback accepting that event type.
            options: Delivery options; ``None`` uses an ongoing subscription.

        Returns:
            A token used to cancel the registration.
        """
        ...
