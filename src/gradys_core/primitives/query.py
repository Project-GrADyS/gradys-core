"""Pair query commands with the event types that carry their responses."""

import abc
from typing import Protocol, Self

from gradys_core.primitives import BaseCommand, BaseEvent


class BaseQuery[E: BaseEvent](BaseCommand, abc.ABC):
    """Base for a command whose response is an event of type ``E``.

    Concrete queries supply a ``command_id``, payload, and ``response_type``.
    This pairing enables typed query handles; it does not provide request IDs,
    response correlation, or delivery guarantees.
    """

    @classmethod
    def query_types(cls) -> tuple[type[Self], type[E]]:
        """Expose the concrete query and its response together for type inference."""
        return cls, cls.response_type()

    @classmethod
    @abc.abstractmethod
    def response_type(cls) -> type[E]:
        """Return the event class expected in response to this query command."""
        ...


class QueryDefinition[C: BaseCommand, R: BaseEvent](Protocol):
    """Structural pairing of a command type ``C`` and response event type ``R``."""
    @classmethod
    def query_types(cls) -> tuple[type[C], type[R]]:
        """Return the command class and its response event class, in that order."""
        ...
