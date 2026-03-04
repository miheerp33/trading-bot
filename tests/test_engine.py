"""Tests for the paper trading engine: Signal, RiskManager, runner, MACrossover."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from engine.risk import RiskManager
from engine.runner import run_paper
from engine.signal import Signal
from execution.paper_broker import PaperBroker
from data_sources.mock_source import MockDataSource
from strategies.ma_crossover import MACrossover


# ---------------------------------------------------------------------------
# Signal
# ---------------------------------------------------------------------------


def test_signal_frozen():
    sig = Signal(action="BUY", symbol="AAPL", target_qty=10)
    with pytest.raises((AttributeError, TypeError)):
        sig.target_qty = 20  # type: ignore[misc]


def test_signal_defaults():
    sig = Signal(action="HOLD", symbol="AAPL", target_qty=0)
    assert sig.limit_price is None
    assert sig.stop_price is None
    assert sig.timestamp is not None


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------


def _make_broker(cash: float = 10_000.0) -> PaperBroker:
    return PaperBroker(cash=cash)


def test_risk_hold_returns_none():
    risk = RiskManager()
    broker = _make_broker()
    sig = Signal(action="HOLD", symbol="AAPL", target_qty=10)
    assert risk.size_order(sig, broker, price=100.0) is None


def test_risk_buy_creates_order():
    risk = RiskManager(max_position_size=50)
    broker = _make_broker(cash=5000.0)
    sig = Signal(action="BUY", symbol="AAPL", target_qty=20)
    order = risk.size_order(sig, broker, price=100.0)
    assert order is not None
    assert order.action == "BUY"
    assert order.quantity == 20


def test_risk_buy_capped_by_max_position():
    risk = RiskManager(max_position_size=10)
    broker = _make_broker(cash=50_000.0)
    sig = Signal(action="BUY", symbol="AAPL", target_qty=50)
    order = risk.size_order(sig, broker, price=100.0)
    assert order is not None
    assert order.quantity == 10


def test_risk_buy_no_cap():
    """max_position_size=None: only cash limits the buy."""
    risk = RiskManager(max_position_size=None)
    broker = _make_broker(cash=5_000.0)
    sig = Signal(action="BUY", symbol="AAPL", target_qty=99_999)
    order = risk.size_order(sig, broker, price=100.0)
    assert order is not None
    assert order.quantity == 50  # 5000 // 100


def test_risk_buy_capped_by_cash():
    risk = RiskManager(max_position_size=100)
    broker = _make_broker(cash=500.0)  # can only afford 5 shares at $100
    sig = Signal(action="BUY", symbol="AAPL", target_qty=20)
    order = risk.size_order(sig, broker, price=100.0)
    assert order is not None
    assert order.quantity == 5


def test_risk_buy_no_cash_returns_none():
    risk = RiskManager()
    broker = _make_broker(cash=0.0)
    sig = Signal(action="BUY", symbol="AAPL", target_qty=10)
    assert risk.size_order(sig, broker, price=100.0) is None


def test_risk_sell_reduces_position():
    risk = RiskManager()
    broker = _make_broker(cash=5000.0)
    broker.positions["AAPL"] = 15
    sig = Signal(action="SELL", symbol="AAPL", target_qty=0)
    order = risk.size_order(sig, broker, price=100.0)
    assert order is not None
    assert order.action == "SELL"
    assert order.quantity == 15


def test_risk_sell_no_position_returns_none():
    risk = RiskManager()
    broker = _make_broker()
    sig = Signal(action="SELL", symbol="AAPL", target_qty=0)
    assert risk.size_order(sig, broker, price=100.0) is None


def test_risk_daily_loss_limit():
    risk = RiskManager(daily_loss_limit=500.0)
    broker = _make_broker(cash=9_000.0)
    risk.reset_day(10_000.0)  # SOD equity = 10k
    sig = Signal(action="BUY", symbol="AAPL", target_qty=10)
    # current equity 9k = -1k drawdown > 500 limit
    order = risk.size_order(sig, broker, price=100.0, current_equity=9_000.0)
    assert order is None


def test_risk_daily_loss_within_limit():
    risk = RiskManager(daily_loss_limit=500.0)
    broker = _make_broker(cash=9_600.0)
    risk.reset_day(10_000.0)
    sig = Signal(action="BUY", symbol="AAPL", target_qty=5)
    order = risk.size_order(sig, broker, price=100.0, current_equity=9_700.0)
    assert order is not None


# ---------------------------------------------------------------------------
# MACrossover strategy
# ---------------------------------------------------------------------------


def _feed(strategy: MACrossover, prices: list[float]) -> list[list[Signal]]:
    """Feed prices one at a time; returns list of signal batches per tick."""
    return [strategy.on_tick({"AAPL": p}) for p in prices]


def test_ma_crossover_no_signal_before_warmup():
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=10)
    results = _feed(strat, [100.0, 101.0, 102.0])
    assert all(len(batch) == 0 for batch in results)


def test_ma_crossover_validation():
    with pytest.raises(ValueError):
        MACrossover(symbol="AAPL", short_window=10, long_window=5)


def test_ma_crossover_buy_signal():
    """Rising prices → short MA crosses above long MA → BUY."""
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=10)
    # Flat then rising prices to force a crossover
    prices = [100.0, 100.0, 100.0, 100.0,  # fill buffer, MAs equal
              110.0, 120.0]                  # short MA jumps above long MA
    batches = _feed(strat, prices)
    buy_signals = [s for batch in batches for s in batch if s.action == "BUY"]
    assert len(buy_signals) >= 1
    assert buy_signals[0].target_qty == 10


def test_ma_crossover_sell_signal():
    """Falling prices after rising → short MA crosses below long MA → SELL."""
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=10)
    prices = [100.0, 110.0, 120.0, 130.0,  # rising
              80.0, 70.0]                    # sharp drop
    batches = _feed(strat, prices)
    sell_signals = [s for batch in batches for s in batch if s.action == "SELL"]
    assert len(sell_signals) >= 1
    assert sell_signals[0].target_qty == 0


# ---------------------------------------------------------------------------
# run_paper integration
# ---------------------------------------------------------------------------


def _crossover_ticks(n: int) -> list[dict[str, float]]:
    """Flat prices then a jump — guarantees a bullish MA crossover around tick 5.

    With short_window=2, long_window=4:
    - Ticks 1-4: price=100 → deque fills, MAs equal (100 == 100).
    - Tick 5:    price=110 → short_ma=105 > long_ma=102.5, prev equal → BUY.
    """
    prices = [100.0] * 4 + [110.0] + [105.0] * max(0, n - 5)
    return [{"AAPL": p} for p in prices[:n]]


def test_run_paper_creates_csv_files(tmp_path: Path):
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=5)
    broker = PaperBroker(cash=10_000.0)
    risk = RiskManager(max_position_size=50)
    ticks = _crossover_ticks(30)
    ds = MockDataSource(ticks=ticks)

    run_paper(strat, ds, broker, risk, symbols=["AAPL"], interval=0, max_ticks=30, output_dir=tmp_path)

    fills = list(tmp_path.glob("fills_*.csv"))
    equity = list(tmp_path.glob("equity_*.csv"))
    assert len(fills) == 1
    assert len(equity) == 1


def test_run_paper_equity_rows(tmp_path: Path):
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=5)
    broker = PaperBroker(cash=10_000.0)
    risk = RiskManager(max_position_size=50)
    ticks = _crossover_ticks(30)
    ds = MockDataSource(ticks=ticks)

    run_paper(strat, ds, broker, risk, symbols=["AAPL"], interval=0, max_ticks=30, output_dir=tmp_path)

    eq_file = next(tmp_path.glob("equity_*.csv"))
    rows = list(csv.DictReader(eq_file.open()))
    assert len(rows) == 30
    for row in rows:
        assert float(row["equity"]) > 0


def test_run_paper_fill_recorded_on_crossover(tmp_path: Path):
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=5)
    broker = PaperBroker(cash=10_000.0)
    risk = RiskManager(max_position_size=50)
    ticks = _crossover_ticks(30)
    ds = MockDataSource(ticks=ticks)

    run_paper(strat, ds, broker, risk, symbols=["AAPL"], interval=0, max_ticks=30, output_dir=tmp_path)

    fills_file = next(tmp_path.glob("fills_*.csv"))
    rows = list(csv.DictReader(fills_file.open()))
    assert len(rows) >= 1
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["action"] == "BUY"


def test_run_paper_cash_decreases_after_buy(tmp_path: Path):
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=5)
    broker = PaperBroker(cash=10_000.0)
    risk = RiskManager(max_position_size=50)
    ticks = _crossover_ticks(30)
    ds = MockDataSource(ticks=ticks)

    run_paper(strat, ds, broker, risk, symbols=["AAPL"], interval=0, max_ticks=30, output_dir=tmp_path)

    assert broker.cash < 10_000.0


def test_run_paper_respects_max_ticks(tmp_path: Path):
    """MockDataSource cycles; run_paper must stop at max_ticks."""
    strat = MACrossover(symbol="AAPL", short_window=2, long_window=4, target_qty=5)
    broker = PaperBroker(cash=10_000.0)
    risk = RiskManager()
    ds = MockDataSource(ticks=[{"AAPL": 100.0}])

    run_paper(strat, ds, broker, risk, symbols=["AAPL"], interval=0, max_ticks=5, output_dir=tmp_path)

    eq_file = next(tmp_path.glob("equity_*.csv"))
    rows = list(csv.DictReader(eq_file.open()))
    assert len(rows) == 5
