from __future__ import annotations

from strategy.basic_strategy import generate_signal


def test_generate_signal_none_when_price_missing() -> None:
    assert generate_signal({"symbol": "AAPL", "last_price": None}) is None


def test_generate_signal_buy_above_threshold() -> None:
    assert generate_signal({"symbol": "AAPL", "last_price": 200}) == {
        "action": "BUY",
        "symbol": "AAPL",
    }


def test_generate_signal_sell_below_threshold() -> None:
    assert generate_signal({"symbol": "AAPL", "last_price": 100}) == {
        "action": "SELL",
        "symbol": "AAPL",
    }
