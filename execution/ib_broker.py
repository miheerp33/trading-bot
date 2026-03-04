from __future__ import annotations

from config.settings import SETTINGS
from execution.broker import Fill, Order
from utils.ib_client import ib_connection


class IBBroker:
    def submit_market_order(self, order: Order, *, price: float) -> Fill:
        # For IB, "price" is informational (market order). We return a best-effort fill record.
        with ib_connection(client_id=SETTINGS.ib_client_id_execution) as ib:
            from ib_insync import MarketOrder, Stock  # lazy import

            contract = Stock(order.symbol, "SMART", "USD")
            ib.placeOrder(contract, MarketOrder(order.action, order.quantity))
            ib.sleep(2)

        return Fill(symbol=order.symbol, action=order.action, quantity=order.quantity, price=price)

