class ProtocolSetUpException(Exception):
    """Exception raised for errors in the setup process.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)