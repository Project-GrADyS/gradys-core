# Protocol showcases

Run from the repository root with gradys-core installed:

```bash
python -m showcases.success
python -m showcases.failures
python -m showcases.plugins
```

`success.py` initializes local state in the constructor and obtains handles in
synchronous `run(context)`. Handles remain usable after run returns.
`failures.py` shows immediate capability validation and error propagation.
`plugins.py` shares a ProtocolContext with plugins for command and event access.

`MockEnvironment.bind()` constructs `ProtocolContext(Connection(self))` and calls
`protocol.run(context)`. Connection forwards operations immediately; this example
adapter queues accepted commands until `start()` and emits lifecycle events.
Subscriptions return cancellation callbacks. Environment scheduling is independent
of the synchronous protocol/context API.
