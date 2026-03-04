from config.settings import SETTINGS
from data.fetch_data import fetch_latest_price
from execution.ib_broker import IBBroker
from execution.order_executor import execute_order
from execution.paper_broker import PaperBroker
from strategy.basic_strategy import generate_signal
from utils.logger import get_logger

logger = get_logger()


def run_bot():
    logger.info("Starting trading bot...")

    if SETTINGS.execution_mode == "ib":
        broker = IBBroker()
    else:
        broker = PaperBroker(cash=SETTINGS.paper_starting_cash)

    # Fetch market data
    market_data = fetch_latest_price()
    logger.info(f"Market Data: {market_data}")

    # Generate trade signal
    signal = generate_signal(market_data)
    logger.info(f"Strategy Signal: {signal}")

    # Execute trade if signal exists
    if signal:
        price = float(market_data.get("last_price") or 0)
        fill = execute_order(signal, broker, price=price)
        logger.info(f"Fill: {fill}")
        if SETTINGS.execution_mode != "ib":
            logger.info(f"Paper cash: {broker.cash}, positions: {broker.positions}")
    else:
        logger.info("No trade signal. Holding position.")

if __name__ == "__main__":
    run_bot()
