"""Shared protocol contracts for simulation and embedded execution environments.

Protocols declare command, event, and query requirements through the
``ProtocolContext`` supplied to their synchronous ``run`` method. Environment adapters implement the structural interface
in ``gradys_core.environment``; reusable message definitions live in
``gradys_core.primitives`` and ``gradys_core.capabilities``.
"""
