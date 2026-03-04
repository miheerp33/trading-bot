# utils/market_data.py

import logging

from config.settings import SETTINGS
from utils.ib_client import ib_connection


def fetch_delayed_price(
    symbol: str,
    exchange: str = "SMART",
    currency: str = "USD",
    client_id: int = 101,
) -> dict:
    """
    Fetch delayed snapshot market data for a given symbol using IB API.

    :param symbol: Ticker symbol (e.g., "AAPL")
    :param exchange: Exchange to route the order through (default: "SMART")
    :param currency: Currency (default: "USD")
    :param client_id: Unique client ID for the session
    :return: Dictionary with last price, bid, ask
    """
    try:
        with ib_connection(client_id=client_id) as ib:
            from ib_insync import Stock  # lazy import

            logging.info(f"Connected to IBKR API for symbol: {symbol}")

            contract = Stock(symbol, exchange, currency)
            ib.qualifyContracts(contract)

            # Use delayed snapshot
            ticker = ib.reqMktData(contract, "", snapshot=True, regulatorySnapshot=False)
            ib.sleep(2)  # Give TWS a second to respond

            return {
                "symbol": symbol,
                "last": ticker.last,
                "bid": ticker.bid,
                "ask": ticker.ask,
                "host": SETTINGS.ib_host,
                "port": SETTINGS.ib_port,
            }

    except Exception as e:
        logging.error(f"Market data fetch failed: {e}")
        return {}
