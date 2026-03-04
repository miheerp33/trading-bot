from __future__ import annotations

import os
from dataclasses import dataclass


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    # IB Gateway / TWS connection
    ib_host: str = os.getenv("IB_HOST", "host.docker.internal")
    ib_port: int = _getenv_int("IB_PORT", 7497)  # 7497 paper, 7496 live

    # Client IDs (keep unique per process/module)
    ib_client_id_market_data: int = _getenv_int("IB_CLIENT_ID_MARKET_DATA", 101)
    ib_client_id_execution: int = _getenv_int("IB_CLIENT_ID_EXECUTION", 102)

    # Strategy parameters
    symbol: str = os.getenv("SYMBOL", "AAPL")
    short_window: int = _getenv_int("SHORT_WINDOW", 5)
    long_window: int = _getenv_int("LONG_WINDOW", 20)

    # Trading parameters
    order_quantity: int = _getenv_int("ORDER_QUANTITY", 10)

    # Execution mode: "paper" (default) or "ib"
    execution_mode: str = os.getenv("EXECUTION_MODE", "paper").strip().lower()

    # Paper trading
    paper_starting_cash: float = float(os.getenv("PAPER_STARTING_CASH", "100000"))


SETTINGS = Settings()

