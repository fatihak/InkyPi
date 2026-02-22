import hmac
import hashlib
import base64
import urllib.parse
import time
import logging

logger = logging.getLogger(__name__)

BASE = "https://api.kraken.com"

# Kraken internal symbols → standard symbols
_SYM = {
    "XXBT": "BTC", "XBT": "BTC",
    "XETH": "ETH", "XLTC": "LTC",
    "XXRP": "XRP", "XXLM": "XLM",
    "XDOT": "DOT", "XZEC": "ZEC",
    "XXMR": "XMR", "XADA": "ADA",
    "XSOL": "SOL", "ZUSD": "USD",
    "ZEUR": "EUR", "ZGBP": "GBP",
    "ZCAD": "CAD",
}
_STABLES = {"USD", "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP"}
_FIAT    = {"EUR", "GBP", "CAD", "JPY", "AUD", "CHF"}


def _normalize(sym):
    return _SYM.get(sym, sym)


def _sign(urlpath, data, secret):
    encoded = (str(data["nonce"]) + urllib.parse.urlencode(data)).encode()
    message = urlpath.encode() + hashlib.sha256(encoded).digest()
    mac = hmac.new(base64.b64decode(secret), message, hashlib.sha512)
    return base64.b64encode(mac.digest()).decode()


def _post(session, path, api_key, api_secret, data=None):
    data = dict(data or {})
    data["nonce"] = str(int(time.time() * 1000))
    headers = {"API-Key": api_key, "API-Sign": _sign(path, data, api_secret)}
    resp = session.post(f"{BASE}{path}", data=data, headers=headers, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("error"):
        raise RuntimeError(", ".join(body["error"]))
    return body["result"]


def _get_prices(session, symbols, currency):
    """Fetch {symbol: price_in_currency} from Kraken public ticker."""
    prices = {}
    to_fetch = []
    for sym in symbols:
        if sym == currency:
            prices[sym] = 1.0
        elif sym in _STABLES and currency == "USD":
            prices[sym] = 1.0
        else:
            to_fetch.append(sym)

    if not to_fetch:
        return prices

    # Build pairs: try BTCUSD, ETHUSD, etc.
    pair_map = {}  # pair_string -> symbol
    for sym in to_fetch:
        pair_map[f"{sym}{currency}"] = sym
        pair_map[f"X{sym}Z{currency}"] = sym  # Kraken alt format

    try:
        resp = session.get(
            f"{BASE}/0/public/Ticker",
            params={"pair": ",".join(pair_map.keys())},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("result", {})
        for pair_key, info in data.items():
            last = float(info["c"][0])
            # Match returned pair back to symbol
            for sym in to_fetch:
                if sym in pair_key or f"X{sym}" in pair_key:
                    prices[sym] = last
                    break
    except Exception as e:
        logger.warning("Kraken ticker fetch failed: %s", e)

    return prices


def fetch(api_key, api_secret, currency="USD", trade_limit=5):
    """Returns {'holdings': [...], 'trades': [...], 'errors': [...]}"""
    from utils.http_client import get_http_session
    session = get_http_session()
    errors = []

    # ── Balances ──────────────────────────────────────────────────────────
    holdings = []
    try:
        raw = _post(session, "/0/private/Balance", api_key, api_secret)
        balances = {}
        for raw_sym, amount_str in raw.items():
            amount = float(amount_str)
            if amount < 1e-8:
                continue
            sym = _normalize(raw_sym)
            balances[sym] = balances.get(sym, 0.0) + amount

        prices = _get_prices(session, list(balances.keys()), currency)

        for sym, amount in balances.items():
            price = prices.get(sym, 0.0)
            holdings.append({
                "symbol":   sym,
                "amount":   amount,
                "value":    round(amount * price, 2),
                "price":    price,
                "exchange": "Kraken",
            })
        holdings.sort(key=lambda x: x["value"], reverse=True)
    except Exception as e:
        errors.append(f"Kraken balances: {e}")

    # ── Recent trades ─────────────────────────────────────────────────────
    trades = []
    try:
        result = _post(session, "/0/private/TradesHistory", api_key, api_secret)
        raw_trades = sorted(
            result.get("trades", {}).values(),
            key=lambda t: float(t.get("time", 0)),
            reverse=True,
        )
        for t in raw_trades[:trade_limit]:
            pair = t.get("pair", "")
            # Strip quote currency from pair (USD/EUR/XBT/ETH)
            sym = pair
            for quote in [currency, "USD", "EUR", "XBT", "ETH", "BTC"]:
                xquote = f"Z{quote}" if len(quote) == 3 else quote
                for prefix in [f"X{quote}", xquote, quote]:
                    if sym.endswith(prefix):
                        sym = sym[:-len(prefix)]
                        break
                if sym != pair:
                    break
            sym = _normalize(sym)
            ts = float(t.get("time", 0))
            trades.append({
                "timestamp": ts,
                "date_str":  _fmt_time(ts),
                "type":      t.get("type", "").upper(),
                "symbol":    sym,
                "amount":    float(t.get("vol", 0)),
                "cost":      float(t.get("cost", 0)),
                "exchange":  "Kraken",
            })
    except Exception as e:
        logger.warning("Kraken trade history: %s", e)
        errors.append(f"Kraken trades: {e}")

    return {"holdings": holdings, "trades": trades, "errors": errors}


def _fmt_time(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%d.%m %H:%M")
