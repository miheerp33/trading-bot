from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("trading_bot.yfinance")


@dataclass
class YFinanceSource:
    """Fetches prices and historical data via yfinance (no auth required).

    Suitable for daily runs (GitHub Actions) and backtesting.
    Not suitable for intraday / tick-level strategies.
    """

    def get_prices(self, symbols: list[str]) -> dict[str, float]:
        """Return the most recent closing price for each symbol."""
        import yfinance as yf  # lazy import — not needed for paper-only runs

        result: dict[str, float] = {}
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period="2d")
                if hist.empty:
                    logger.warning("yfinance: no data for %s", symbol)
                    continue
                price = float(hist["Close"].iloc[-1])
                result[symbol] = price
            except Exception as exc:
                logger.error("yfinance price fetch failed for %s: %s", symbol, exc)
        return result

    @staticmethod
    def get_history(symbol: str, days: int = 210) -> list[float]:
        """Return the last `days` daily closing prices for a symbol.

        Used to seed the SSOSMAFilter before the first tick so the 200-day SMA
        is available immediately without a live warm-up period.
        """
        import yfinance as yf

        period = f"{days + 20}d"  # fetch a little extra to account for holidays
        hist = yf.download(symbol, period=period, auto_adjust=True, progress=False)
        if hist.empty:
            raise ValueError(f"yfinance returned no history for {symbol}")
        closes = hist["Close"].squeeze().dropna().tolist()
        return closes[-days:]
