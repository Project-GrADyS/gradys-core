"""Tiny demonstration of deriving protocol requirements from their usage sites."""

from collections.abc import Callable, Iterable
from typing import Any


class Event:
    pass


class Command:
    pass


def subscribe(event: type[Event]) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    O decorator adiciona uma marca ao método para indicar que ele requer um evento específico.
    Essa marca é usada posteriormente para verificar se o protocolo que está sendo implementado
    possuirá os eventos necessários.
    """

    def decorate(method: Callable[..., Any]) -> Callable[..., Any]:

        setattr(method, "required_event", event)
        return method

    return decorate


def command(command_type: type[Command]) -> Callable[..., None]:
    """
    A função command é usada para criar um método que envia um comando específico. Ela adiciona uma marca ao método para indicar
    que ele requer um comando específico. Essa marca é usada posteriormente para verificar se o protocolo que está sendo implementado
    possuirá os comandos necessários.
    """

    def send(*args: Any, **kwargs: Any) -> None:
        print(f"send {command_type.__name__}{args[1:]!r}{kwargs!r}")

    send.required_command = command_type  # type: ignore[attr-defined]
    return send


class Protocol:
    """
    A classe base do protocolo não precisa de nenhuma declaração manual de eventos ou comandos. Em vez disso, 
    ela coleta automaticamente os requisitos de eventos e comandos a partir dos métodos decorados com @subscribe e command.
    """
    required_events: set[type[Event]] = set()
    required_commands: set[type[Command]] = set()

    def __init_subclass__(cls) -> None:
        """Collect requirements left on the subclass by the two helpers above."""
        cls.required_events = set().union(
            *(base.required_events for base in cls.__bases__ if issubclass(base, Protocol))
        )
        cls.required_commands = set().union(
            *(base.required_commands for base in cls.__bases__ if issubclass(base, Protocol))
        )

        for member in vars(cls).values():
            if event := getattr(member, "required_event", None):
                cls.required_events.add(event)
            if command_type := getattr(member, "required_command", None):
                cls.required_commands.add(command_type)

    @classmethod
    def bind(
        cls,
        supported_events: Iterable[type[Event]],
        supported_commands: Iterable[type[Command]],
    ) -> "Protocol":
        missing_events = cls.required_events - set(supported_events)
        missing_commands = cls.required_commands - set(supported_commands)

        if missing_events or missing_commands:
            def names(items: Iterable[type[Any]]) -> str:
                return ", ".join(sorted(item.__name__ for item in items)) or "none"
            raise RuntimeError(
                f"Cannot bind {cls.__name__}: "
                f"missing events [{names(missing_events)}]; "
                f"missing commands [{names(missing_commands)}]"
            )

        return cls()


# A few example capabilities.
class Start(Event):
    pass


class Telemetry(Event):
    pass


class Stop(Event):
    pass


class Move(Command):
    pass


class Broadcast(Command):
    pass


class Land(Command):
    pass


class ExampleProtocol(Protocol):
    move = command(Move)
    broadcast = command(Broadcast)

    @subscribe(Start)
    def on_start(self, event: Start) -> None:
        self.move(10, 20)

    @subscribe(Telemetry)
    def on_telemetry(self, event: Telemetry) -> None:
        self.broadcast("position received")


# Includes needed Move/Start, unnecessary Land/Stop, and omits Broadcast/Telemetry.
SUPPORTED_EVENTS = [Start, Stop]
SUPPORTED_COMMANDS = [Move, Land]


if __name__ == "__main__":
    ExampleProtocol.bind(SUPPORTED_EVENTS, SUPPORTED_COMMANDS)
