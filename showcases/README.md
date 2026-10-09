# Protocol showcases

From the repository root, with `gradys-core` installed in the active Python environment:

```bash
python -m showcases.success
python -m showcases.failures
python -m showcases.plugins
```

`success.py` shows constructor-time subscriptions and commands, a lifecycle event, mobility updates, and a requirement made after binding. `failures.py` shows missing command and event capabilities, a failed connection that cannot be reused, and a missing capability requested after binding. `plugins.py` shows a plugin that receives the protocol in its constructor and registers through it: the plugin's requirements merge into the protocol's (a missing one rejects the whole protocol), overlapping requirements are deduplicated, and every event reaches all subscribers with no per-owner isolation.

`mock_environment.py` is a small example of the environment side. Its `MobilityHandler` declares the command it accepts and event it produces. `MockEnvironment` uses those declarations to implement the `Environment` interface from `gradys_core.environment`, without inheriting from it, and binds protocols with `protocol._inject(self)`. Its methods accept commands, register event handlers, and check capabilities. Algorithm implementations import `BaseProtocol` and handles from `gradys_core.protocol`; their commands and events are shared definitions in `gradys_core.capabilities`. Commands accepted during injection execute only after `start()`.
