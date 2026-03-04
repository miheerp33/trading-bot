from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from execution.broker import Order
from execution.paper_broker import PaperBroker
from engine.signal import Signal


@dataclass
class RiskManager:
    """Converts a Signal into a sized Order, enforcing position and loss limits.

    Rules applied in order:
    1. HOLD signals → no order.
    2. Compute delta = target_qty - current_position (long-only: target >= 0).
    3. Cap the target at max_position_size.
    4. For BUY: ensure broker has enough cash; trim qty to what cash covers.
    5. For SELL: clamp so we never go short (long-only policy).
    6. If daily_loss_limit is set and today's loss exceeds the limit → no order.
    """

    max_position_size: int | None = 100  # None = no cap (full capital allocation)
    daily_loss_limit: float | None = None  # max drawdown from start-of-day equity

    _sod_equity: float = field(init=False, default=0.0)
    _sod_date: date = field(init=False, default_factory=date.today)

    def reset_day(self, equity: float) -> None:
        """Call once at the start of each trading day with current equity."""
        self._sod_date = date.today()
        self._sod_equity = equity

    def check_daily_loss(self, current_equity: float) -> bool:
        """Return True if trading is allowed (loss limit not breached)."""
        if self.daily_loss_limit is None or self._sod_equity == 0.0:
            return True
        daily_pnl = current_equity - self._sod_equity
        return daily_pnl >= -self.daily_loss_limit

    def size_order(
        self,
        signal: Signal,
        broker: PaperBroker,
        price: float,
        current_equity: float | None = None,
    ) -> Order | None:
        """Return an Order or None if nothing should be submitted."""
        if signal.action == "HOLD":
            return None

        if current_equity is not None and not self.check_daily_loss(current_equity):
            return None

        current_pos = broker.positions.get(signal.symbol, 0)

        # Clamp target to [0, max_position_size] (long-only); None = no cap
        target = signal.target_qty
        if self.max_position_size is not None:
            target = min(target, self.max_position_size)
        target = max(target, 0)

        delta = target - current_pos

        if delta == 0:
            return None

        action = "BUY" if delta > 0 else "SELL"
        qty = abs(delta)

        if action == "BUY":
            affordable = int(broker.cash // price)
            qty = min(qty, affordable)
            if qty <= 0:
                return None
        else:
            # Long-only: never sell more than we hold
            qty = min(qty, max(current_pos, 0))
            if qty <= 0:
                return None

        return Order(symbol=signal.symbol, action=action, quantity=qty)
