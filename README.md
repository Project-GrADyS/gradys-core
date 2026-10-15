# gradys-core

An extensible, typed protocol interface for simulation and embedded execution
environments. Protocols use commands, events, and callback-based queries through
an environment-provided `ProtocolContext`. All operations are synchronous.

## Implement a protocol

`BaseProtocol.run(context)` is abstract: every concrete protocol must implement it.
Constructors initialize configuration and local state. Obtain environment handles
inside `run`, where the connection is already available:

```python
from gradys_core.capabilities.mobility import GotoCoords, PositionUpdate
from gradys_core.protocol import BaseProtocol, ProtocolContext


class MoveProtocol(BaseProtocol):
    def __init__(self, destination: tuple[float, float, float]) -> None:
        self.destination = destination
        self.positions: list[PositionUpdate] = []

    def run(self, context: ProtocolContext) -> None:
        context.require_event(PositionUpdate).subscribe(self.positions.append)
        self.move = context.require_command(GotoCoords)
        self.move.send(GotoCoords(*self.destination))
```

Handles retain their connection and remain usable from callbacks after `run`
returns. Plugins receive the same context and request their own capabilities.
No call to a base constructor is required.

## Connect an environment

An adapter implements the structural `Environment` interface: `command_sender`,
`command_checker`, `event_subscriber`, and `event_checker`. Event registration
returns a callable that removes that registration.

```python
from gradys_core.connection import Connection
from gradys_core.protocol import ProtocolContext

# environment is an adapter implementing gradys_core.environment.Environment.
protocol = MoveProtocol((1.0, 2.0, 3.0))
context = ProtocolContext(Connection(environment))
protocol.run(context)
```

`Connection(environment)` is ready immediately. There is no injection step or
buffer/replay phase. Operations are forwarded in call order. The environment
chooses when to invoke `run`, execute accepted commands, and deliver lifecycle
and other events. Core does not enforce single invocation or roll back effects.

Each `require_*` validates support immediately and raises `ProtocolSetUpException`
on rejection. Previous actions remain in effect. Repeated requirements are allowed
and checked each time. Obtaining a handle alone neither sends nor subscribes.

## Commands, events, and queries

- `context.require_command(CommandType)` returns a `CommandHandle[CommandType]`.
  `send(command)` forwards a command; returning does not imply execution completed.
- `context.require_event(EventType)` returns an `EventHandle[EventType]`.
  `subscribe(callback)` returns a cancellation token. Use
  `options=SubscriptionOptions(once=True)` for at most one delivery.
- `context.require_query(QueryType)` checks both command and response support and
  returns a `QueryHandle[CommandType, ResponseType]`.
  `request(command, on_response)` subscribes before sending and returns a token.

Define a query by extending `BaseQuery[ResponseType]` and implementing the
`response_type()` class method, or provide the structural `QueryDefinition`
contract. Queries remain callback-based: a response may arrive before `request`
returns. They consume the next matching response event, without request IDs or
timeouts; simultaneous requests may receive the same event.

## Migrating from constructor-time operations

Move `self.require_*` calls and environment operations from `__init__` to
`run(self, context: ProtocolContext)`, using `context.require_*`. Pass the context
to plugins instead of the protocol. Replace `_inject(environment)` with the
explicit construction and invocation above. Register callbacks before sending
commands whose immediate events they need to receive.

## Development

Install development dependencies and run the checks:

```bash
pip install -e ".[dev]"
./check.sh
```

The checks cover Ruff, pytest, mypy, and Pyright. Static tests preserve handle
and query-response typing. See [showcases](showcases/README.md) for runnable
examples of protocol execution, capability errors, and shared plugin contexts.
