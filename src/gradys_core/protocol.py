from typing import Type, Optional

from gradys_core.command import BaseCommand, CommandId, CommandHandle, CommandSender
from gradys_core.event import BaseEvent, EventId, EventHandle, EventSubscriber, EventHandler


class BaseProtocol:
    _required_commands: set[CommandId]
    _required_events: set[EventId]

    _linked: bool

    # Mechanisms installed during linking
    _command_sender: Optional[CommandSender]
    _event_subscriber: Optional[EventSubscriber]

    def __init__(self):
        self._linked = False
        self._command_handles = set()
        self._required_events = set()

        self._command_sender = None
        self._event_subscriber = None

    def require_command[C: BaseCommand](self, command: Type[C]) -> CommandHandle[C]:
        if self._linked:
            raise RuntimeError("Cannot register commands after protocol is linked.")

        command_id = command.command_id

        if command_id in self._required_commands:
            raise ValueError(f"Command with id '{command_id}' is already registered.")

        self._required_commands.add(command_id)

        return CommandHandle[C](lambda: self._command_sender)

    def require_event[E: BaseEvent](self, event: Type[E]) -> EventHandle[E]:
        if self._linked:
            raise RuntimeError("Cannot register events after protocol is linked.")

        event_id = event.event_id
        if event_id in self._required_events:
            raise ValueError(f"Event with id '{event_id}' is already registered.")

        self._required_events.add(event_id)
        return EventHandle[E](lambda: self._event_subscriber)
