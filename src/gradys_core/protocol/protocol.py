"""User-facing protocol base class."""

from abc import ABC, abstractmethod

from .context import ProtocolContext


class BaseProtocol(ABC):
    """Implement an algorithm whose environment is supplied when execution starts.

    Constructors may initialize local state and configuration. Environment
    adapters call start with a connected context when ready to execute protocol
    operations. No base constructor or environment injection is required.
    """

    @abstractmethod
    async def start(self, context: ProtocolContext) -> None:
        """Execute asynchronously using the supplied context.

        Implementations obtain handles from context and may retain them for
        event callbacks after start returns. Errors propagate to the caller;
        previously performed actions are not rolled back. Invocation timing
        and lifecycle events remain the environment adapter's responsibility.
        """
        ...
