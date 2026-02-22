from plugins.base_plugin.base_plugin import BasePlugin
import logging

logger = logging.getLogger(__name__)


def _fmt_value(v, currency="USD"):
    symbol = "€" if currency == "EUR" else "$"
    if v >= 1_000_000:
        return f"{symbol}{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{symbol}{v:,.0f}"
    if v >= 1:
        return f"{symbol}{v:.2f}"
    return f"{symbol}{v:.4f}"


def _fmt_amount(amount, symbol):
    if symbol in ("BTC", "ETH"):
        return f"{amount:.6f}".rstrip("0").rstrip(".")
    if amount >= 1000:
        return f"{amount:,.0f}"
    if amount >= 1:
        return f"{amount:.4f}".rstrip("0").rstrip(".")
    return f"{amount:.6f}".rstrip("0").rstrip(".")


class CryptoPortfolio(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["style_settings"] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        currency      = settings.get("currency", "USD")
        max_holdings  = int(settings.get("max_holdings", 8))
        max_trades    = int(settings.get("max_trades", 5))
        show_trades   = settings.get("show_trades", "true") == "true"
        use_kraken    = settings.get("use_kraken", "false") == "true"
        use_coinbase  = settings.get("use_coinbase", "false") == "true"

        if not use_kraken and not use_coinbase:
            raise RuntimeError("No exchange enabled. Enable Kraken and/or Coinbase in settings.")

        all_holdings = []
        all_trades   = []
        all_errors   = []
        active_exchanges = []

        if use_kraken:
            key    = settings.get("kraken_api_key", "").strip()
            secret = settings.get("kraken_api_secret", "").strip()
            if not key or not secret:
                all_errors.append("Kraken API key/secret not configured")
            else:
                try:
                    from plugins.crypto_portfolio.exchanges import kraken
                    result = kraken.fetch(key, secret, currency, trade_limit=max_trades)
                    all_holdings.extend(result["holdings"])
                    all_trades.extend(result["trades"])
                    all_errors.extend(result["errors"])
                    if not result["errors"]:
                        active_exchanges.append("Kraken")
                except Exception as e:
                    all_errors.append(f"Kraken: {e}")

        if use_coinbase:
            key    = settings.get("coinbase_api_key", "").strip()
            secret = settings.get("coinbase_api_secret", "").strip()
            if not key or not secret:
                all_errors.append("Coinbase API key/secret not configured")
            else:
                try:
                    from plugins.crypto_portfolio.exchanges import coinbase
                    result = coinbase.fetch(key, secret, currency, trade_limit=max_trades)
                    all_holdings.extend(result["holdings"])
                    all_trades.extend(result["trades"])
                    all_errors.extend(result["errors"])
                    if not result["errors"]:
                        active_exchanges.append("Coinbase")
                except Exception as e:
                    all_errors.append(f"Coinbase: {e}")

        if not all_holdings and all_errors:
            raise RuntimeError("Could not fetch portfolio: " + " | ".join(all_errors))

        # Merge duplicate symbols across exchanges
        merged = {}
        for h in all_holdings:
            sym = h["symbol"]
            if sym in merged:
                merged[sym]["amount"] += h["amount"]
                merged[sym]["value"]  += h["value"]
                merged[sym]["exchange"] = "Multi"
            else:
                merged[sym] = dict(h)
        all_holdings = sorted(merged.values(), key=lambda x: x["value"], reverse=True)

        total_value = sum(h["value"] for h in all_holdings)
        asset_count = len(all_holdings)

        # Portfolio composition (Crypto / Stablecoin / Fiat)
        _STABLES = {"USD", "USDT", "USDC", "BUSD", "DAI", "TUSD", "USDP", "USDD", "FRAX"}
        _FIAT    = {"EUR", "GBP", "CAD", "JPY", "AUD", "CHF"}
        if total_value > 0:
            stable_val  = sum(h["value"] for h in all_holdings if h["symbol"] in _STABLES)
            fiat_val    = sum(h["value"] for h in all_holdings if h["symbol"] in _FIAT)
            stable_pct  = round(stable_val / total_value * 100)
            fiat_pct    = round(fiat_val   / total_value * 100)
            crypto_pct  = max(0, 100 - stable_pct - fiat_pct)
        else:
            crypto_pct = stable_pct = fiat_pct = 0

        # Add percentage of total
        for h in all_holdings:
            h["pct"] = round(h["value"] / total_value * 100, 1) if total_value > 0 else 0
            h["value_fmt"]  = _fmt_value(h["value"], currency)
            h["amount_fmt"] = _fmt_amount(h["amount"], h["symbol"])

        # Sort and limit trades
        all_trades.sort(key=lambda x: x["timestamp"], reverse=True)
        all_trades = all_trades[:max_trades]

        cur_symbol = "€" if currency == "EUR" else "$"
        template_params = {
            "total_value":      _fmt_value(total_value, currency),
            "currency_symbol":  cur_symbol,
            "holdings":         all_holdings[:max_holdings],
            "trades":           all_trades,
            "show_trades":      show_trades,
            "active_exchanges": active_exchanges,
            "asset_count":      asset_count,
            "crypto_pct":       crypto_pct,
            "stable_pct":       stable_pct,
            "fiat_pct":         fiat_pct,
            "errors":           all_errors,
            "plugin_settings":  settings,
        }

        return self.render_image(
            dimensions,
            "crypto_portfolio.html",
            "crypto_portfolio.css",
            template_params,
        )
