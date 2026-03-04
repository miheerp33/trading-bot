from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from engine.signal import Signal


@dataclass
class MACrossover:
    """Moving-average crossover strategy for a single symbol.

    Emits BUY when short_window MA crosses above long_window MA,
    SELL (target_qty=0) when it crosses below, HOLD otherwise.

    Params:
        symbol:        Ticker to trade.
        short_window:  Fast MA period.
        long_window:   Slow MA period.
        target_qty:    Desired long position size on a BUY signal.
    """

    symbol: str
    short_window: int = 5
    long_window: int = 20
    target_qty: int = 10

    _prices: deque[float] = field(init=False, repr=False)
    _prev_short_ma: float | None = field(init=False, default=None)
    _prev_long_ma: float | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if self.short_window >= self.long_window:
            raise ValueError("short_window must be < long_window")
        self._prices = deque(maxlen=self.long_window)

    def on_tick(self, prices: dict[str, float]) -> list[Signal]:
        price = prices.get(self.symbol)
        if price is None:
            return []

        self._prices.append(price)

        if len(self._prices) < self.long_window:
            return []  # not enough data yet

        short_ma = sum(list(self._prices)[-self.short_window :]) / self.short_window
        long_ma = sum(self._prices) / self.long_window

        prev_short = self._prev_short_ma
        prev_long = self._prev_long_ma

        self._prev_short_ma = short_ma
        self._prev_long_ma = long_ma

        if prev_short is None or prev_long is None:
            return []  # need two ticks of MAs to detect a cross

        # Bullish crossover: short crosses above long
        if prev_short <= prev_long and short_ma > long_ma:
            return [Signal(action="BUY", symbol=self.symbol, target_qty=self.target_qty)]

        # Bearish crossover: short crosses below long
        if prev_short >= prev_long and short_ma < long_ma:
            return [Signal(action="SELL", symbol=self.symbol, target_qty=0)]

        return []  # no crossover this tick
