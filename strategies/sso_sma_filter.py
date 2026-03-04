from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from engine.signal import Signal

# Large placeholder — risk layer trims to what cash can actually buy.
_FULL_ALLOCATION = 99_999


@dataclass
class SSOSMAFilter:
    """200-day SMA trend filter: hold SSO when above SMA, SHY otherwise.

    Designed for once-daily runs (GitHub Actions cron).  On each tick:
    - If SSO price > 200-day SMA and we're not already in SSO → rotate to SSO.
    - If SSO price ≤ 200-day SMA and we're not already in SHY → rotate to SHY.
    - Otherwise → no action (empty list).

    Emits two signals per rotation: SELL the exiting asset first, then BUY the
    entering asset.  The runner processes SELL before BUY so cash is freed first.

    Params:
        sso:             SSO ticker (default "SSO").
        shy:             SHY ticker (default "SHY").
        sma_period:      Lookback window in trading days (default 200).
        initial_history: Seed prices (e.g. from yfinance) so the SMA is ready
                         on the first tick without a long warm-up period.
    """

    sso: str = "SSO"
    shy: str = "SHY"
    sma_period: int = 200

    # Seed with historical SSO closes from yfinance before the first tick.
    initial_history: list[float] = field(default_factory=list)

    _sso_prices: deque[float] = field(init=False, repr=False)
    # Track which asset we currently "hold" to avoid redundant rotations.
    _in_sso: bool | None = field(init=False, default=None)  # None = unknown

    def __post_init__(self) -> None:
        self._sso_prices = deque(
            self.initial_history[-self.sma_period :], maxlen=self.sma_period
        )

    @property
    def is_warmed_up(self) -> bool:
        return len(self._sso_prices) >= self.sma_period

    def on_tick(self, prices: dict[str, float]) -> list[Signal]:
        sso_price = prices.get(self.sso)
        if sso_price is None:
            return []

        self._sso_prices.append(sso_price)

        if not self.is_warmed_up:
            return []

        sma = sum(self._sso_prices) / self.sma_period
        above_sma = sso_price > sma

        # No regime change → nothing to do.
        if above_sma and self._in_sso is True:
            return []
        if not above_sma and self._in_sso is False:
            return []

        if above_sma:
            # Rotate into SSO: sell SHY first, then buy SSO.
            self._in_sso = True
            return [
                Signal(action="SELL", symbol=self.shy, target_qty=0),
                Signal(action="BUY", symbol=self.sso, target_qty=_FULL_ALLOCATION),
            ]
        else:
            # Rotate into SHY: sell SSO first, then buy SHY.
            self._in_sso = False
            return [
                Signal(action="SELL", symbol=self.sso, target_qty=0),
                Signal(action="BUY", symbol=self.shy, target_qty=_FULL_ALLOCATION),
            ]
