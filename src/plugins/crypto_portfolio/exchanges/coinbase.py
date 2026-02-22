import hmac
import hashlib
import time
import logging

logger = logging.getLogger(__name__)

BASE = "https://api.coinbase.com"


def _headers(api_key, api_secret, method, path, body=""):
    ts = str(int(time.time()))
    msg = ts + method.upper() + path + body
    sig = hmac.new(api_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return {
        "CB-ACCESS-KEY":       api_key,
        "CB-ACCESS-SIGN":      sig,
        "CB-ACCESS-TIMESTAMP": ts,
        "CB-VERSION":          "2021-04-01",
    }


def _get(session, api_key, api_secret, path, params=None):
    resp = session.get(
        f"{BASE}{path}",
        headers=_headers(api_key, api_secret, "GET", path),
        params=params,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def fetch(api_key, api_secret, currency="USD", trade_limit=5):
    """Returns {'holdings': [...], 'trades': [...], 'errors': [...]}"""
    from utils.http_client import get_http_session
    session = get_http_session()
    errors = []

    # ── Accounts / Balances ───────────────────────────────────────────────
    accounts = []
    holdings = []
    try:
        path = "/v2/accounts"
        while path:
            data = _get(session, api_key, api_secret, path, params={"limit": 100})
            accounts.extend(data.get("data", []))
            next_uri = data.get("pagination", {}).get("next_uri")
            path = next_uri if next_uri else None

        for acc in accounts:
            amount = float(acc.get("balance", {}).get("amount", 0))
            if amount < 1e-8:
                continue
            symbol   = acc.get("balance",        {}).get("currency", "")
            native   = acc.get("native_balance",  {})
            nat_cur  = native.get("currency", "USD")
            nat_val  = float(native.get("amount", 0))

            # Convert to requested currency if needed (best-effort)
            value = nat_val if nat_cur == currency else nat_val
            price = value / amount if amount > 0 else 0.0

            holdings.append({
                "symbol":   symbol,
                "amount":   amount,
                "value":    round(value, 2),
                "price":    price,
                "exchange": "Coinbase",
                "_acc_id":  acc.get("id"),
            })
        holdings.sort(key=lambda x: x["value"], reverse=True)
    except Exception as e:
        errors.append(f"Coinbase balances: {e}")

    # ── Recent transactions ───────────────────────────────────────────────
    trades = []
    try:
        # Only fetch transactions for non-zero accounts (top 10 by value)
        top_accounts = [h for h in holdings if h.get("_acc_id")][:10]
        for h in top_accounts:
            acc_id = h["_acc_id"]
            try:
                data = _get(
                    session, api_key, api_secret,
                    f"/v2/accounts/{acc_id}/transactions",
                    params={"limit": trade_limit},
                )
                for txn in data.get("data", []):
                    txn_type = txn.get("type", "")
                    if txn_type not in ("buy", "sell", "send", "receive", "trade"):
                        continue
                    amount_data = txn.get("amount", {})
                    native      = txn.get("native_amount", {})
                    created_at  = txn.get("created_at", "")
                    trades.append({
                        "timestamp": _parse_ts(created_at),
                        "date_str":  _fmt_iso(created_at),
                        "type":      txn_type.upper(),
                        "symbol":    amount_data.get("currency", h["symbol"]),
                        "amount":    abs(float(amount_data.get("amount", 0))),
                        "cost":      abs(float(native.get("amount", 0))),
                        "exchange":  "Coinbase",
                    })
            except Exception as e:
                logger.warning("Coinbase txn fetch for %s: %s", h["symbol"], e)

        trades.sort(key=lambda x: x["timestamp"], reverse=True)
        trades = trades[:trade_limit]
    except Exception as e:
        logger.warning("Coinbase trades: %s", e)
        errors.append(f"Coinbase trades: {e}")

    # Strip internal fields before returning
    for h in holdings:
        h.pop("_acc_id", None)

    return {"holdings": holdings, "trades": trades, "errors": errors}


def _parse_ts(iso):
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.timestamp()
    except Exception:
        return 0.0


def _fmt_iso(iso):
    try:
        from datetime import datetime, timezone
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d.%m %H:%M")
    except Exception:
        return iso[:10] if iso else ""
