from config.settings import SETTINGS
from execution.broker import Order


def execute_order(signal, broker, *, price: float):
    order = Order(
        symbol=signal["symbol"],
        action=signal["action"],
        quantity=SETTINGS.order_quantity,
    )
    return broker.submit_market_order(order, price=price)
