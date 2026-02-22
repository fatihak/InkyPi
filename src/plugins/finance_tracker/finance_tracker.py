from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
from urllib.parse import quote as urlquote
import logging

logger = logging.getLogger(__name__)

COINGECKO_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_CHART_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
YAHOO_CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"

# Common crypto IDs for CoinGecko
CRYPTO_IDS = {
    "btc": "bitcoin", "eth": "ethereum", "sol": "solana",
    "ada": "cardano", "dot": "polkadot", "doge": "dogecoin",
    "xrp": "ripple", "ltc": "litecoin", "avax": "avalanche-2",
    "matic": "matic-network", "link": "chainlink", "bnb": "binancecoin",
    "atom": "cosmos", "uni": "uniswap", "algo": "algorand",
    "near": "near", "ftm": "fantom", "shib": "shiba-inu",
    "bitcoin": "bitcoin", "ethereum": "ethereum", "solana": "solana",
    "cardano": "cardano", "polkadot": "polkadot", "dogecoin": "dogecoin",
    "ripple": "ripple", "litecoin": "litecoin", "cosmos": "cosmos",
    "uniswap": "uniswap", "algorand": "algorand",
}

# Common commodity/index symbols routed to Yahoo Finance
YAHOO_SYMBOLS = {
    "gold": "GC=F", "silver": "SI=F", "oil": "CL=F",
    "sp500": "^GSPC", "nasdaq": "^IXIC", "dow": "^DJI",
    # Major crypto via Yahoo Finance (no API key required)
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
    "solana": "SOL-USD", "sol": "SOL-USD",
    "cardano": "ADA-USD", "ada": "ADA-USD",
    "dogecoin": "DOGE-USD", "doge": "DOGE-USD",
    "ripple": "XRP-USD", "xrp": "XRP-USD",
    "litecoin": "LTC-USD", "ltc": "LTC-USD",
    "avalanche": "AVAX-USD", "avax": "AVAX-USD",
    "chainlink": "LINK-USD", "link": "LINK-USD",
    "bnb": "BNB-USD",
    "cosmos": "ATOM-USD", "atom": "ATOM-USD",
    "uniswap": "UNI-USD", "uni": "UNI-USD",
    "algorand": "ALGO-USD", "algo": "ALGO-USD",
    "near": "NEAR-USD",
    "shib": "SHIB-USD", "shiba": "SHIB-USD",
}

# Display names: CoinGecko ID -> (Ticker, Full Name)
CRYPTO_DISPLAY = {
    "bitcoin": ("BTC", "Bitcoin"), "ethereum": ("ETH", "Ethereum"),
    "solana": ("SOL", "Solana"), "cardano": ("ADA", "Cardano"),
    "polkadot": ("DOT", "Polkadot"), "dogecoin": ("DOGE", "Dogecoin"),
    "ripple": ("XRP", "Ripple"), "litecoin": ("LTC", "Litecoin"),
    "avalanche-2": ("AVAX", "Avalanche"), "matic-network": ("MATIC", "Polygon"),
    "chainlink": ("LINK", "Chainlink"), "binancecoin": ("BNB", "BNB"),
    "cosmos": ("ATOM", "Cosmos"), "uniswap": ("UNI", "Uniswap"),
    "algorand": ("ALGO", "Algorand"), "near": ("NEAR", "Near"),
    "fantom": ("FTM", "Fantom"), "shiba-inu": ("SHIB", "Shiba Inu"),
}

# Yahoo symbol -> display name
YAHOO_DISPLAY = {
    "GC=F": ("GC", "Gold"), "SI=F": ("SI", "Silver"), "CL=F": ("CL", "Oil"),
    "^GSPC": ("SPX", "S&P 500"), "^IXIC": ("NDX", "Nasdaq"), "^DJI": ("DJI", "Dow Jones"),
    "BTC-USD": ("BTC", "Bitcoin"), "ETH-USD": ("ETH", "Ethereum"),
    "SOL-USD": ("SOL", "Solana"), "ADA-USD": ("ADA", "Cardano"),
    "DOGE-USD": ("DOGE", "Dogecoin"), "XRP-USD": ("XRP", "Ripple"),
    "LTC-USD": ("LTC", "Litecoin"), "AVAX-USD": ("AVAX", "Avalanche"),
    "LINK-USD": ("LINK", "Chainlink"), "BNB-USD": ("BNB", "BNB"),
    "ATOM-USD": ("ATOM", "Cosmos"), "UNI-USD": ("UNI", "Uniswap"),
    "ALGO-USD": ("ALGO", "Algorand"), "NEAR-USD": ("NEAR", "Near"),
    "SHIB-USD": ("SHIB", "Shiba Inu"),
}

# Symbols that should go through Yahoo Finance (stocks, ETFs, commodities)
# CoinGecko IDs are lowercase alpha; Yahoo symbols contain uppercase or special chars
def is_yahoo_symbol(symbol):
    return symbol != symbol.lower() or "=" in symbol or "." in symbol


class FinanceTracker(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        assets_raw = settings.get("assets", "bitcoin,ethereum")
        currency = settings.get("currency", "usd").lower()
        timeframe = settings.get("timeframe", "24h")

        asset_list = [a.strip() for a in assets_raw.split(",") if a.strip()]

        crypto_ids = []
        yahoo_symbols = []
        for asset in asset_list:
            lower = asset.lower()
            if lower in YAHOO_SYMBOLS:
                yahoo_symbols.append(YAHOO_SYMBOLS[lower])
            elif is_yahoo_symbol(asset):
                yahoo_symbols.append(asset)
            else:
                coin_id = CRYPTO_IDS.get(lower, lower)
                crypto_ids.append(coin_id)

        assets_data = []

        # Fetch crypto data from CoinGecko
        if crypto_ids:
            assets_data.extend(self._fetch_crypto(crypto_ids, currency, timeframe))

        # Fetch stock/commodity data from Yahoo Finance
        for symbol in yahoo_symbols:
            data = self._fetch_yahoo(symbol, currency, timeframe)
            if data:
                assets_data.append(data)

        if not assets_data:
            raise RuntimeError("No asset data could be retrieved. Check your asset list.")

        for asset in assets_data:
            price = asset.get("price")
            if price is not None:
                asset["price_display"] = f"{price:,.2f}" if price < 10000 else f"{price:,.0f}"
            else:
                asset["price_display"] = None

        template_params = {
            "assets": assets_data,
            "currency": currency.upper(),
            "currency_symbol": "$" if currency == "usd" else "\u20ac" if currency == "eur" else "\u00a3" if currency == "gbp" else "",
            "timeframe": timeframe,
            "plugin_settings": settings,
        }

        image = self.render_image(
            dimensions, "finance_tracker.html", "finance_tracker.css", template_params
        )
        return image

    def _fetch_crypto(self, coin_ids, currency, timeframe):
        session = get_http_session()
        results = []

        # Fetch current prices
        try:
            resp = session.get(
                COINGECKO_PRICE_URL,
                params={
                    "ids": ",".join(coin_ids),
                    "vs_currencies": currency,
                    "include_24hr_change": "true",
                    "include_7d_change": "true",
                },
                timeout=30,
            )
            resp.raise_for_status()
            price_data = resp.json()
        except Exception as e:
            logger.error("CoinGecko price fetch failed: %s", e)
            price_data = {}

        for coin_id in coin_ids:
            coin_prices = price_data.get(coin_id, {})
            price = coin_prices.get(currency)
            if timeframe == "7d":
                change = coin_prices.get(f"{currency}_7d_change")
            else:
                change = coin_prices.get(f"{currency}_24h_change")

            sparkline = self._fetch_crypto_sparkline(coin_id, currency, timeframe)

            ticker, full_name = CRYPTO_DISPLAY.get(
                coin_id, (coin_id.upper()[:5], coin_id.replace("-", " ").title())
            )
            results.append({
                "symbol": ticker,
                "name": full_name,
                "price": price,
                "change": round(change, 2) if change is not None else None,
                "sparkline": sparkline,
            })

        return results

    def _fetch_crypto_sparkline(self, coin_id, currency, timeframe):
        session = get_http_session()
        days = "7" if timeframe == "7d" else "1"
        try:
            resp = session.get(
                COINGECKO_CHART_URL.format(coin_id=coin_id),
                params={"vs_currency": currency, "days": days},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            prices = [p[1] for p in data.get("prices", [])]
            return self._downsample(prices, 30)
        except Exception as e:
            logger.error("CoinGecko sparkline fetch failed for %s: %s", coin_id, e)
            return []

    def _fetch_yahoo(self, symbol, currency, timeframe):
        session = get_http_session()
        # Try preferred range first, fall back to 5d if no data (e.g. weekends)
        range_val = "1d" if timeframe == "24h" else "7d"
        interval = "15m" if timeframe == "24h" else "1d"

        for attempt_range, attempt_interval in [(range_val, interval), ("5d", "1d")]:
            try:
                resp = session.get(
                    YAHOO_CHART_URL.format(symbol=urlquote(symbol, safe='')),
                    params={"interval": attempt_interval, "range": attempt_range},
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                result = data["chart"]["result"][0]
                meta = result["meta"]
                quote = result["indicators"]["quote"][0]
                closes = [c for c in quote.get("close", []) if c is not None]
                if closes:
                    break
            except Exception as e:
                logger.error("Yahoo Finance fetch failed for %s (%s): %s", symbol, attempt_range, e)
                meta = {}
                closes = []
        else:
            # Both attempts failed or returned no data
            ticker, full_name = YAHOO_DISPLAY.get(symbol, (symbol.upper(), symbol))
            return {
                "symbol": ticker,
                "name": full_name,
                "price": None,
                "change": None,
                "sparkline": [],
            }

        current_price = meta.get("regularMarketPrice", closes[-1] if closes else None)
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")

        change = None
        if current_price and prev_close and prev_close != 0:
            change = round(((current_price - prev_close) / prev_close) * 100, 2)

        ticker, full_name = YAHOO_DISPLAY.get(
            symbol, (symbol.upper(), meta.get("shortName", symbol))
        )
        return {
            "symbol": ticker,
            "name": full_name,
            "price": current_price,
            "change": change,
            "sparkline": self._downsample(closes, 30),
        }

    def _downsample(self, data, target_points):
        if not data:
            return []
        if len(data) <= target_points:
            return data
        step = len(data) / target_points
        return [data[int(i * step)] for i in range(target_points)]
