
from typing import ClassVar, Protocol, Callable, Optional

type CommandId = str

class BaseCommand:
  command_id: ClassVar[CommandId]

type CommandSender = Callable[[BaseCommand], None]

class CommandHandle[C: BaseCommand]:
    def __init__(self, get_sender: Callable[[], Optional[CommandSender]]):
        self._get_sender = get_sender

    def send(self, command: C) -> None:
      sender = self._get_sender()

      if sender is None:
          raise RuntimeError("Command sender is not set. Protocol might not be linked.")
      sender(command)