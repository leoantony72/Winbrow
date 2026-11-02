"""Serialize shared agent state while allowing scoped child dispatch."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class _Lease:
    owner: object
    active: bool = True


_lease: ContextVar[_Lease | None] = ContextVar("winbrow_execution_lease", default=None)


class ExecutionOwnership:
    """A goal and its awaited children share ownership, not unrelated requests.

    A separate dispatch lock serializes individual tools within that goal. A
    lease expires on exit so detached children cannot retain stale ownership.
    """

    def __init__(self):
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def hold(self):
        inherited = _lease.get()
        if inherited is not None and inherited.owner is self and inherited.active:
            yield
            return
        async with self._lock:
            lease = _Lease(self)
            token = _lease.set(lease)
            try:
                yield
            finally:
                lease.active = False
                _lease.reset(token)
