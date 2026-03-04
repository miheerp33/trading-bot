def generate_signal(market_data):
    price = market_data["last_price"]

    # Placeholder logic: simple threshold
    if price is None:
        return None

    if price > 150:  # placeholder threshold
        return {"action": "BUY", "symbol": market_data["symbol"]}
    elif price < 130:
        return {"action": "SELL", "symbol": market_data["symbol"]}
    else:
        return None
