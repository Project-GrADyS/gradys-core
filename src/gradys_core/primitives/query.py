import abc
from typing import Self

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
