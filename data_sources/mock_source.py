from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class MockDataSource:
    """Replays a fixed sequence of price dicts — useful for tests and backtests.

    Cycles back to the start when exhausted (use finite max_ticks in run_paper
    to avoid an infinite loop during tests).
    """

    ticks: list[dict[str, float]]
    _idx: int = field(init=False, default=0)

    def get_prices(self, symbols: list[str]) -> dict[str, float]:
        if not self.ticks:
            return {}
        prices = self.ticks[self._idx % len(self.ticks)]
        self._idx += 1
        return {s: prices[s] for s in symbols if s in prices}


@dataclass
class StreamDataSource:
    """Wraps an iterator/generator of price dicts (for more controlled replay)."""

    _queue: deque[dict[str, float]] = field(default_factory=deque, init=False)

    def push(self, prices: dict[str, float]) -> None:
        self._queue.append(prices)

    def get_prices(self, symbols: list[str]) -> dict[str, float]:
        if not self._queue:
            return {}
        prices = self._queue.popleft()
        return {s: prices[s] for s in symbols if s in prices}
