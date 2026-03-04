from __future__ import annotations

import csv
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

from execution.paper_broker import PaperBroker
from engine.risk import RiskManager
from engine.signal import DataSource, Signal, Strategy

logger = logging.getLogger("trading_bot.runner")


def _calc_equity(broker: PaperBroker, prices: dict[str, float]) -> float:
    mark = sum(qty * prices.get(sym, 0.0) for sym, qty in broker.positions.items())
    return broker.cash + mark


def _process_signal(
    signal: Signal,
    broker: PaperBroker,
    risk: RiskManager,
    prices: dict[str, float],
    equity: float,
    ts: datetime,
    fills_writer: csv.DictWriter,
    ff,
) -> float:
    """Submit one signal through risk → broker. Returns updated equity."""
    price = prices.get(signal.symbol)
    if price is None:
        logger.warning("No price for %s, skipping.", signal.symbol)
        return equity

    order = risk.size_order(signal, broker, price, current_equity=equity)
    if order is None:
        logger.info("Risk blocked order for %s.", signal.symbol)
        return equity

    try:
        fill = broker.submit_market_order(order, price=price)
        logger.info(
            "Fill: %s %d %s @ %.2f  cash=%.2f",
            fill.action, fill.quantity, fill.symbol, fill.price, broker.cash,
        )
        fills_writer.writerow({
            "timestamp": ts.isoformat(),
            "symbol": fill.symbol,
            "action": fill.action,
            "quantity": fill.quantity,
            "price": fill.price,
            "cash_after": f"{broker.cash:.2f}",
        })
        ff.flush()
        equity = _calc_equity(broker, prices)
    except ValueError as exc:
        logger.error("Order rejected by broker: %s", exc)

    return equity


def run_paper(
    strategy: Strategy,
    data_source: DataSource,
    broker: PaperBroker,
    risk: RiskManager,
    symbols: list[str],
    *,
    interval: float = 60.0,
    max_ticks: int | None = None,
    output_dir: str | Path = "data",
) -> None:
    """Main paper-trading loop.

    Each tick:
    1. Pull latest prices from data_source.
    2. Refresh day tracking (SOD equity reset) if date changed.
    3. Ask strategy for a list of Signals.
    4. Process SELL signals first, then BUY (to free cash before buying).
    5. Append fills and equity snapshot to CSV files under output_dir.

    Args:
        interval:  Seconds between ticks (0 = as fast as possible).
        max_ticks: Stop after N ticks (None = run until KeyboardInterrupt).
        output_dir: Directory for output CSVs (created if absent).
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    fills_path = out / f"fills_{run_id}.csv"
    equity_path = out / f"equity_{run_id}.csv"

    fills_cols = ["timestamp", "symbol", "action", "quantity", "price", "cash_after"]
    equity_cols = ["timestamp", "cash", "equity"]

    with fills_path.open("w", newline="") as ff, equity_path.open("w", newline="") as ef:
        fills_writer = csv.DictWriter(ff, fieldnames=fills_cols)
        equity_writer = csv.DictWriter(ef, fieldnames=equity_cols)
        fills_writer.writeheader()
        equity_writer.writeheader()

        current_day: date | None = None
        tick = 0

        logger.info("Paper trading started. run_id=%s symbols=%s", run_id, symbols)

        try:
            while max_ticks is None or tick < max_ticks:
                tick += 1
                ts = datetime.now(timezone.utc)

                # --- Pull prices (single call per tick) ---
                prices = _safe_get_prices(data_source, symbols)
                if not prices:
                    logger.warning("Tick %d: no prices returned, skipping.", tick)
                    _maybe_sleep(interval)
                    continue

                equity = _calc_equity(broker, prices)

                # --- Reset day tracking using current prices ---
                today = ts.date()
                if today != current_day:
                    risk.reset_day(equity)
                    current_day = today
                    logger.info("New trading day %s — SOD equity=%.2f", today, equity)

                # --- Ask strategy ---
                signals: list[Signal] = strategy.on_tick(prices)

                if signals:
                    # SELL before BUY so proceeds are available for the buy leg
                    ordered = sorted(signals, key=lambda s: 0 if s.action == "SELL" else 1)
                    for signal in ordered:
                        if signal.action == "HOLD":
                            continue
                        logger.info(
                            "Tick %d: signal=%s %s target_qty=%d",
                            tick, signal.action, signal.symbol, signal.target_qty,
                        )
                        equity = _process_signal(
                            signal, broker, risk, prices, equity, ts, fills_writer, ff
                        )
                else:
                    logger.debug("Tick %d: no signals — equity=%.2f", tick, equity)

                # --- Always write equity snapshot ---
                equity_writer.writerow({
                    "timestamp": ts.isoformat(),
                    "cash": f"{broker.cash:.2f}",
                    "equity": f"{equity:.2f}",
                })
                ef.flush()

                _maybe_sleep(interval)

        except KeyboardInterrupt:
            logger.info("Paper trading stopped by user after %d ticks.", tick)

    logger.info("Fills  → %s", fills_path)
    logger.info("Equity → %s", equity_path)


def _safe_get_prices(data_source: DataSource, symbols: list[str]) -> dict[str, float]:
    try:
        return data_source.get_prices(symbols)
    except Exception as exc:
        logger.error("DataSource error: %s", exc)
        return {}


def _maybe_sleep(interval: float) -> None:
    if interval > 0:
        time.sleep(interval)
