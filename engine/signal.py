from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Protocol, runtime_checkable

Action = Literal["BUY", "SELL", "HOLD"]


@dataclass(frozen=True)
class Signal:
    """Typed decision emitted by a strategy each tick.

    target_qty is the desired absolute long position (0 = flat).
    action is BUY | SELL | HOLD — HOLD short-circuits the risk layer.
    The risk layer is responsible for computing the delta and sizing the order.
    """

    action: Action
    symbol: str
    target_qty: int  # desired long position after fill (>= 0)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    limit_price: float | None = None
    stop_price: float | None = None


@runtime_checkable
class Strategy(Protocol):
    """A strategy receives the latest prices and returns a list of Signals.

    An empty list means no action this tick.
    Multiple signals in one list are processed SELL-before-BUY by the runner.
    """

    def on_tick(self, prices: dict[str, float]) -> list[Signal]: ...


@runtime_checkable
class DataSource(Protocol):
    """Fetches the latest prices for a list of symbols."""

    def get_prices(self, symbols: list[str]) -> dict[str, float]: ...
