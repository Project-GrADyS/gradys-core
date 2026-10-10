import abc
from typing import Protocol, Self

from gradys_core.primitives import BaseCommand, BaseEvent

class BaseQuery[E: BaseEvent](BaseCommand, abc.ABC):
    @classmethod
    def query_types(cls) -> tuple[type[Self], type[E]]:
        """Expose the concrete query and its response together for type inference."""
        return cls, cls.response_type()

    @classmethod
    @abc.abstractmethod
    def response_type(cls) -> type[E]:
        """Returns the type of the event that is expected in response to this query."""
        ...


class QueryDefinition[C: BaseCommand, R: BaseEvent](Protocol):
    """
    A protocol for defining a query with a specific command and response type.
    This exists to facilitate type-checking of the query and its response.
    """
    @classmethod
    def query_types(cls) -> tuple[type[C], type[R]]: ...
