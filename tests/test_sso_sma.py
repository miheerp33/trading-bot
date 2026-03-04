"""Tests for SSOSMAFilter strategy and its integration with run_paper."""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from data_sources.mock_source import MockDataSource
from engine.risk import RiskManager
from engine.runner import run_paper
from execution.paper_broker import PaperBroker
from strategies.sso_sma_filter import SSOSMAFilter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SMA = 10  # use short SMA for fast tests


def _make_strategy(history: list[float]) -> SSOSMAFilter:
    return SSOSMAFilter(sso="SSO", shy="SHY", sma_period=SMA, initial_history=history)


def _flat(n: int, price: float = 100.0) -> list[float]:
    return [price] * n


# ---------------------------------------------------------------------------
# Warmup
# ---------------------------------------------------------------------------


def test_no_signal_before_warmup():
    """Strategy returns [] when fewer than sma_period prices have been seen."""
    strat = SSOSMAFilter(sso="SSO", shy="SHY", sma_period=SMA)
    for p in _flat(SMA - 1):
        result = strat.on_tick({"SSO": p, "SHY": 85.0})
        assert result == []


def test_warmed_up_after_sma_period_ticks():
    strat = SSOSMAFilter(sso="SSO", shy="SHY", sma_period=SMA)
    for p in _flat(SMA):
        strat.on_tick({"SSO": p, "SHY": 85.0})
    assert strat.is_warmed_up


def test_initial_history_seeds_warmup():
    """Seeding with sma_period prices means first on_tick is already warmed up."""
    strat = _make_strategy(_flat(SMA))
    assert strat.is_warmed_up


# ---------------------------------------------------------------------------
# Signal direction
# ---------------------------------------------------------------------------


def test_above_sma_emits_buy_sso():
    """Price above SMA → rotate into SSO."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    signals = strat.on_tick({"SSO": 120.0, "SHY": 85.0})  # 120 >> SMA 100
    actions = {s.symbol: s.action for s in signals}
    assert actions.get("SSO") == "BUY"
    assert actions.get("SHY") == "SELL"


def test_below_sma_emits_buy_shy():
    """Price below SMA → rotate into SHY."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    signals = strat.on_tick({"SSO": 80.0, "SHY": 85.0})  # 80 << SMA 100
    actions = {s.symbol: s.action for s in signals}
    assert actions.get("SHY") == "BUY"
    assert actions.get("SSO") == "SELL"


def test_buy_sso_signal_has_large_target_qty():
    """BUY SSO target_qty should be large so risk layer allocates full capital."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    signals = strat.on_tick({"SSO": 120.0, "SHY": 85.0})
    buy = next(s for s in signals if s.action == "BUY")
    assert buy.target_qty >= 1_000


# ---------------------------------------------------------------------------
# No churn — no repeated signals in the same regime
# ---------------------------------------------------------------------------


def test_no_signal_when_already_in_sso():
    """Once in SSO, subsequent ticks above SMA return no signals."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    strat.on_tick({"SSO": 120.0, "SHY": 85.0})  # enters SSO
    # Second tick also above SMA — should be silent
    signals = strat.on_tick({"SSO": 125.0, "SHY": 85.0})
    assert signals == []


def test_no_signal_when_already_in_shy():
    """Once in SHY, subsequent ticks below SMA return no signals."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    strat.on_tick({"SSO": 80.0, "SHY": 85.0})  # enters SHY
    signals = strat.on_tick({"SSO": 75.0, "SHY": 85.0})
    assert signals == []


# ---------------------------------------------------------------------------
# SELL-before-BUY ordering
# ---------------------------------------------------------------------------


def test_signals_ordered_sell_before_buy():
    """The two signals in a rotation should always be SELL first, BUY second."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    signals = strat.on_tick({"SSO": 120.0, "SHY": 85.0})
    assert len(signals) == 2
    assert signals[0].action == "SELL"
    assert signals[1].action == "BUY"


# ---------------------------------------------------------------------------
# Full capital allocation via risk layer
# ---------------------------------------------------------------------------


def test_full_capital_allocation_no_cap(tmp_path: Path):
    """With max_position_size=None, the entire cash balance buys SSO."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    broker = PaperBroker(cash=20_000.0)
    risk = RiskManager(max_position_size=None)

    sso_price = 120.0
    ticks = [{"SSO": sso_price, "SHY": 85.0}]
    ds = MockDataSource(ticks=ticks)

    run_paper(strat, ds, broker, risk, symbols=["SSO", "SHY"],
              interval=0, max_ticks=1, output_dir=tmp_path)

    expected_shares = int(20_000.0 // sso_price)
    assert broker.positions.get("SSO", 0) == expected_shares
    assert broker.cash < sso_price  # nearly all cash deployed


# ---------------------------------------------------------------------------
# Transition: SSO → SHY → SSO
# ---------------------------------------------------------------------------


def test_rotation_sso_to_shy_and_back(tmp_path: Path):
    """Full rotation cycle: start in SSO, drop below SMA, recover above SMA."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    broker = PaperBroker(cash=20_000.0)
    risk = RiskManager(max_position_size=None)

    # Tick 1: above SMA → buy SSO
    # Tick 2: below SMA → sell SSO, buy SHY
    # Tick 3: above SMA again → sell SHY, buy SSO
    ticks = [
        {"SSO": 120.0, "SHY": 85.0},
        {"SSO": 80.0,  "SHY": 85.0},
        {"SSO": 115.0, "SHY": 85.0},
    ]
    ds = MockDataSource(ticks=ticks)

    run_paper(strat, ds, broker, risk, symbols=["SSO", "SHY"],
              interval=0, max_ticks=3, output_dir=tmp_path)

    # After tick 3 we should be back in SSO (not SHY)
    assert broker.positions.get("SSO", 0) > 0
    assert broker.positions.get("SHY", 0) == 0

    fills_file = next(tmp_path.glob("fills_*.csv"))
    rows = list(csv.DictReader(fills_file.open()))
    # Should have: BUY SSO, SELL SSO, BUY SHY, SELL SHY, BUY SSO = 5 fills
    assert len(rows) >= 4


def test_equity_preserved_across_rotation(tmp_path: Path):
    """Equity should stay close to initial cash after a round-trip rotation
    (small slippage from integer share rounding is expected)."""
    history = _flat(SMA, 100.0)
    strat = _make_strategy(history)
    broker = PaperBroker(cash=10_000.0)
    risk = RiskManager(max_position_size=None)

    # Same price throughout so no P&L — just rounding
    ticks = [
        {"SSO": 100.0, "SHY": 100.0},  # buy SSO
        {"SSO": 90.0,  "SHY": 100.0},  # sell SSO, buy SHY
        {"SSO": 110.0, "SHY": 100.0},  # sell SHY, buy SSO
    ]
    ds = MockDataSource(ticks=ticks)

    run_paper(strat, ds, broker, risk, symbols=["SSO", "SHY"],
              interval=0, max_ticks=3, output_dir=tmp_path)

    # Mark-to-market equity should be within $200 of starting (rounding only)
    sso_pos = broker.positions.get("SSO", 0)
    shy_pos = broker.positions.get("SHY", 0)
    equity = broker.cash + sso_pos * 110.0 + shy_pos * 100.0
    assert abs(equity - 10_000.0) < 200
