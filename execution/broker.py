from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Order:
    symbol: str
    action: str  # "BUY" | "SELL"
    quantity: int


@dataclass(frozen=True)
class Fill:
    symbol: str
    action: str
    quantity: int
    price: float


class Broker(Protocol):
    def submit_market_order(self, order: Order, *, price: float) -> Fill: ...

