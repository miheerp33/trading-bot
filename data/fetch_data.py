from config.settings import SETTINGS
from utils.ib_client import ib_connection


def fetch_latest_price():
    with ib_connection(client_id=SETTINGS.ib_client_id_market_data) as ib:
        from ib_insync import Stock  # lazy import

        contract = Stock(SETTINGS.symbol, "SMART", "USD")
        market_data = ib.reqMktData(contract, "", False, False)
        ib.sleep(2)  # allow time to fetch

        price = market_data.last
        return {"symbol": SETTINGS.symbol, "last_price": price}
