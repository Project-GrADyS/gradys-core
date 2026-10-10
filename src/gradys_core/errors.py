"""Exceptions raised while binding protocol requirements to an environment."""


class ProtocolSetUpException(Exception):
    """Report an unsupported command or event capability.

    Attributes:
        message: Explanation of the rejected requirement.
    """

    def __init__(self, message: str):
        """Store the capability failure message as the exception's text."""
        self.message = message
        super().__init__(self.message)
