from __future__ import annotations

from dataclasses import dataclass, field

from execution.broker import Fill, Order


@dataclass
class PaperBroker:
    cash: float
    positions: dict[str, int] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)

    def submit_market_order(self, order: Order, *, price: float) -> Fill:
        if order.quantity <= 0:
            raise ValueError("quantity must be > 0")
        if price <= 0:
            raise ValueError("price must be > 0")

        signed_qty = order.quantity if order.action.upper() == "BUY" else -order.quantity
        cost = signed_qty * price

        # BUY reduces cash; SELL increases cash
        next_cash = self.cash - cost
        if next_cash < 0:
            raise ValueError("insufficient cash for paper fill")

        self.cash = next_cash
        self.positions[order.symbol] = self.positions.get(order.symbol, 0) + signed_qty

        fill = Fill(
            symbol=order.symbol,
            action=order.action.upper(),
            quantity=order.quantity,
            price=price,
        )
        self.fills.append(fill)
        return fill

