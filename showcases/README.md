# Protocol showcases

Run from the repository root with gradys-core installed:

```bash
python -m showcases.success
python -m showcases.failures
python -m showcases.plugins
python -m showcases.queries
```

`success.py` initializes local state in the constructor and obtains handles in
synchronous `run(context)`. Handles remain usable after run returns.
Its async `move_to_destination()` method awaits command acceptance, and the
entry point uses `asyncio.run(main())` to drive the event loop.
`failures.py` shows immediate capability validation and error propagation.
`plugins.py` shares a ProtocolContext with plugins for command and event access.
`queries.py` awaits `request(command)` and receives a typed response event directly.
The environment starts before queries are awaited so queued requests can execute.

`MockEnvironment.bind()` constructs `ProtocolContext(Connection(self))` and calls
`protocol.run(context)`. Requirements and event subscriptions are synchronous;
command sends and query requests must be awaited. This example
adapter queues accepted commands until `start()` and emits lifecycle events.
Subscriptions return cancellation callbacks. Environment scheduling is independent
of protocol setup. Adapters implement async `send_command()` and synchronous
`check_command()`, `check_event()`, and `subscribe_to_event()`.
