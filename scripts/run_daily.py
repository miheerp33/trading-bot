#!/usr/bin/env python3
"""Daily runner for the SSO/SHY 200-day SMA strategy.

Runs once per day via cron (on EC2) or GitHub Actions.

Execution modes — set via EXECUTION_MODE env var:
  paper  (default)  Simulated broker; state persisted to data/paper_state.json.
                    No IB Gateway connection required.  Good for development.
  ib                Real IB paper account via IB Gateway.
                    Reads live cash/positions from IB; submits real paper orders.
                    Requires IB Gateway running at IB_HOST:IB_PORT.

Usage:
    EXECUTION_MODE=paper python scripts/run_daily.py   # simulate
    EXECUTION_MODE=ib    python scripts/run_daily.py   # IB paper account
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.settings import SETTINGS
from data_sources.yfinance_source import YFinanceSource
from engine.risk import RiskManager
from engine.runner import _calc_equity, run_paper
from execution.paper_broker import PaperBroker
from strategies.sso_sma_filter import SSOSMAFilter

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("run_daily")

STATE_FILE = ROOT / "data" / "paper_state.json"
OUTPUT_DIR = ROOT / "data"
STARTING_CASH = 20_000.0
SYMBOLS = ["SSO", "SHY"]
SMA_PERIOD = 200


# ---------------------------------------------------------------------------
# Paper broker helpers (local simulation mode)
# ---------------------------------------------------------------------------

def _load_paper_broker() -> PaperBroker:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())
        broker = PaperBroker(cash=float(state["cash"]))
        broker.positions = {k: int(v) for k, v in state.get("positions", {}).items()}
        logger.info("Paper state loaded: cash=%.2f positions=%s", broker.cash, broker.positions)
        return broker
    logger.info("No state file — starting fresh with $%.0f.", STARTING_CASH)
    return PaperBroker(cash=STARTING_CASH)


def _save_paper_broker(broker: PaperBroker) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps({"cash": broker.cash, "positions": broker.positions}, indent=2)
    )
    logger.info("Paper state saved → %s", STATE_FILE)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    mode = SETTINGS.execution_mode
    logger.info("=== run_daily  mode=%s ===", mode)

    # --- Seed SMA history from yfinance (free, no auth) ---
    ds = YFinanceSource()
    logger.info("Fetching %d days of SSO history for SMA warmup…", SMA_PERIOD + 10)
    history = ds.get_history("SSO", days=SMA_PERIOD + 10)
    logger.info("Fetched %d closing prices.", len(history))

    strategy = SSOSMAFilter(
        sso="SSO", shy="SHY", sma_period=SMA_PERIOD, initial_history=history
    )
    risk = RiskManager(max_position_size=None)

    if mode == "ib":
        _run_ib(strategy, ds, risk)
    else:
        _run_paper(strategy, ds, risk)


def _run_paper(strategy, ds, risk) -> None:
    """Simulate with local PaperBroker — no IB connection needed."""
    broker = _load_paper_broker()

    run_paper(strategy, ds, broker, risk,
              symbols=SYMBOLS, interval=0, max_ticks=1, output_dir=OUTPUT_DIR)

    prices = ds.get_prices(SYMBOLS)
    equity = _calc_equity(broker, prices)
    logger.info(
        "=== EQUITY  cash=%.2f  positions=%s  total=%.2f ===",
        broker.cash, broker.positions, equity,
    )
    _save_paper_broker(broker)


def _run_ib(strategy, ds, risk) -> None:
    """Trade against the real IB paper account via IB Gateway."""
    from execution.ib_sync_broker import IBSyncBroker

    with IBSyncBroker.connect() as broker:
        run_paper(strategy, ds, broker, risk,
                  symbols=SYMBOLS, interval=0, max_ticks=1, output_dir=OUTPUT_DIR)

        prices = ds.get_prices(SYMBOLS)
        equity = _calc_equity(broker, prices)
        logger.info(
            "=== EQUITY  cash=%.2f  positions=%s  total=%.2f ===",
            broker.cash, broker.positions, equity,
        )
        # No state file in IB mode — IB account is the source of truth.


if __name__ == "__main__":
    main()
