from __future__ import annotations

from dataclasses import dataclass

from utils.market_data import fetch_delayed_price


@dataclass
class IBDataSource:
    """Fetches delayed snapshot prices from IB for each symbol.

    Each call to get_prices opens a new IB connection (one per symbol).
    Suitable for low-frequency paper trading; not intended for HFT.
    """

    exchange: str = "SMART"
    currency: str = "USD"
    client_id_base: int = 101  # incremented per symbol to avoid conflicts

    def get_prices(self, symbols: list[str]) -> dict[str, float]:
        result: dict[str, float] = {}
        for i, symbol in enumerate(symbols):
            data = fetch_delayed_price(
                symbol,
                exchange=self.exchange,
                currency=self.currency,
                client_id=self.client_id_base + i,
            )
            price = data.get("last")
            if price and price == price:  # exclude NaN
                result[symbol] = float(price)
        return result
