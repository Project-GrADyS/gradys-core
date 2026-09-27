from typing import ClassVar, Callable, Type

type CommandId = str


class BaseCommand:
    command_id: ClassVar[CommandId]


type CommandSender[C: BaseCommand] = Callable[[C], None]


class CommandHandle[C: BaseCommand]:
    """
    A handle to send commands of a specific type. The handle is created by the protocol and can be used to send commands
    of the specified type to the environment. The handle is type-safe and ensures that only commands of the specified
    type can be sent.
    """

    def __init__(self, command_type: Type[C], sender: CommandSender[C]) -> None:
        self._command = command_type
        self._sender = sender

    def send(self, command: C) -> None:
        if not isinstance(command, self._command):
            raise TypeError(f"Command must be of type {self._command.__name__}, got {type(command).__name__}")
        self._sender(command)