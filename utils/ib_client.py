from __future__ import annotations

import asyncio
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator

from config.settings import SETTINGS

if TYPE_CHECKING:
    from ib_insync import IB


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    """
    Python 3.11+ no longer guarantees a default event loop.
    ib_insync/eventkit expects one at import-time, so we create it explicitly.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        pass

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


@contextmanager
def ib_connection(*, client_id: int) -> Iterator["IB"]:
    """
    Context-managed IB connection with lazy import (avoids import-time asyncio issues).
    """
    ensure_event_loop()
    from ib_insync import IB  # lazy import

    ib = IB()
    ib.connect(SETTINGS.ib_host, SETTINGS.ib_port, clientId=client_id)
    try:
        yield ib
    finally:
        try:
            ib.disconnect()
        except Exception:
            # best-effort disconnect; caller shouldn't crash because of it
            pass

