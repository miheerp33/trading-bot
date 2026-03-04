from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from config.settings import SETTINGS
from execution.broker import Fill, Order
from utils.ib_client import ensure_event_loop

logger = logging.getLogger("trading_bot.ib_sync_broker")

# How long to wait for an IB paper fill before accepting "submitted" status.
# During market hours, market orders fill in < 1 second.
# After hours they get queued — we accept that and move on.
_FILL_TIMEOUT_S = 10


def _read_cash(ib) -> float:
    """Read TotalCashValue from IB account values."""
    for v in ib.accountValues():
        if v.tag == "TotalCashValue" and v.currency == "BASE":
            return float(v.value)
    # Fallback: try USD directly
    for v in ib.accountValues():
        if v.tag == "TotalCashValue" and v.currency == "USD":
            return float(v.value)
    raise RuntimeError("Could not read TotalCashValue from IB account.")


def _read_positions(ib) -> dict[str, int]:
    """Read current non-zero positions from IB account."""
    result: dict[str, int] = {}
    for p in ib.positions():
        qty = int(p.position)
        if qty != 0:
            result[p.contract.symbol] = qty
    return result


class IBSyncBroker:
    """Broker backed by an IB paper (or live) account.

    Mirrors IB account state (cash, positions) into local fields so the
    runner's risk calculations and equity snapshots work correctly mid-run.

    Use as a context manager — connects on entry, disconnects on exit:

        with IBSyncBroker.connect() as broker:
            run_paper(strategy, ds, broker, risk, ...)

    After each fill the local cash and positions are updated immediately.
    The IB account is the authoritative source of truth; on the next daily
    run the state is re-loaded fresh from IB.
    """

    def __init__(self, ib, cash: float, positions: dict[str, int]) -> None:
        self._ib = ib
        self.cash = cash
        self.positions = positions
        self.fills: list[Fill] = []

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def connect(
        cls,
        host: str = SETTINGS.ib_host,
        port: int = SETTINGS.ib_port,
        client_id: int = SETTINGS.ib_client_id_execution,
    ) -> "IBSyncBroker":
        """Connect to IB Gateway and load current account state."""
        ensure_event_loop()
        from ib_insync import IB  # lazy import

        ib = IB()
        logger.info("Connecting to IB Gateway %s:%d (client=%d)…", host, port, client_id)
        ib.connect(host, port, clientId=client_id)
        ib.sleep(3)  # let account data stream in

        cash = _read_cash(ib)
        positions = _read_positions(ib)
        logger.info("Connected.  cash=%.2f  positions=%s", cash, positions)
        return cls(ib, cash, positions)

    def disconnect(self) -> None:
        try:
            self._ib.disconnect()
        except Exception:
            pass
        logger.info("Disconnected from IB Gateway.")

    def __enter__(self) -> "IBSyncBroker":
        return self

    def __exit__(self, *_) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    # Broker interface (same as PaperBroker)
    # ------------------------------------------------------------------

    def submit_market_order(self, order: Order, *, price: float) -> Fill:
        """Place a market order via IB Gateway and wait for fill confirmation.

        If the market is closed and the order is queued (not filled within
        _FILL_TIMEOUT_S), we still update local state using the last known
        price so the rest of the run stays internally consistent.  The real
        IB account will reflect the actual fill price once the order executes.
        """
        from ib_insync import MarketOrder, Stock

        if order.quantity <= 0:
            raise ValueError("quantity must be > 0")

        contract = Stock(order.symbol, "SMART", "USD")
        self._ib.qualifyContracts(contract)

        ib_order = MarketOrder(order.action.upper(), order.quantity)
        trade = self._ib.placeOrder(contract, ib_order)
        logger.info(
            "Submitted: %s %d %s — waiting up to %ds for fill…",
            order.action, order.quantity, order.symbol, _FILL_TIMEOUT_S,
        )

        deadline = time.time() + _FILL_TIMEOUT_S
        while not trade.isDone() and time.time() < deadline:
            self._ib.sleep(0.25)

        status = trade.orderStatus.status
        avg_price = trade.orderStatus.avgFillPrice

        if status == "Filled" and avg_price:
            fill_price = float(avg_price)
            logger.info("Filled @ %.4f", fill_price)
        else:
            # After-hours or slow fill — use supplied price as estimate
            fill_price = price
            logger.warning(
                "Order status='%s' after timeout — using estimated price %.4f. "
                "IB will execute at next available price.",
                status,
                fill_price,
            )

        # Keep local mirrors in sync
        signed_qty = order.quantity if order.action.upper() == "BUY" else -order.quantity
        self.cash -= signed_qty * fill_price
        self.positions[order.symbol] = self.positions.get(order.symbol, 0) + signed_qty
        if self.positions[order.symbol] == 0:
            del self.positions[order.symbol]

        fill = Fill(
            symbol=order.symbol,
            action=order.action.upper(),
            quantity=order.quantity,
            price=fill_price,
        )
        self.fills.append(fill)
        return fill
