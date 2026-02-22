from plugins.base_plugin.base_plugin import BasePlugin
from utils.http_client import get_http_session
import logging
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class AdGuardHome(BasePlugin):

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        host = settings.get("host", "").rstrip("/")
        username = settings.get("username", "")
        password = settings.get("password", "")

        if not host:
            raise RuntimeError("AdGuard Home URL is not configured.")

        auth = (username, password) if username else None

        stats, error = self._fetch_stats(host, auth)
        if stats is None:
            raise RuntimeError(f"Could not connect to AdGuard Home: {error}")

        template_params = {
            "protection_enabled": stats["protection_enabled"],
            "total_queries": stats["total_queries"],
            "blocked_queries": stats["blocked_queries"],
            "blocked_percent": stats["blocked_percent"],
            "safe_browsing": stats["safe_browsing"],
            "safe_search": stats["safe_search"],
            "parental": stats["parental"],
            "avg_processing_ms": stats["avg_processing_ms"],
            "top_clients": stats["top_clients"],
            "rules_count": stats["rules_count"],
            "dns_queries_history": stats["dns_queries_history"],
            "blocked_history": stats["blocked_history"],
            "chart_bars": stats["chart_bars"],
            "version": stats["version"],
            # display toggles
            "show_status": settings.get("show_status", "true") == "true",
            "show_queries": settings.get("show_queries", "true") == "true",
            "show_top_clients": settings.get("show_top_clients", "true") == "true",
            "show_chart": settings.get("show_chart", "true") == "true",
            "show_rules": settings.get("show_rules", "true") == "true",
            # colors
            "color_blocked": settings.get("color_blocked", "#c62828"),
            "color_total": settings.get("color_total", "#cccccc"),
            "plugin_settings": settings,
        }

        return self.render_image(dimensions, "adguard_home.html", "adguard_home.css", template_params)

    def _detect_base(self, session, host, auth):
        """Try /control prefix (direct), then root (reverse proxy). Returns working base or None."""
        for candidate in [f"{host}/control", host]:
            try:
                r = session.get(f"{candidate}/status", auth=auth, timeout=10, verify=False)
                if r.status_code == 200:
                    logger.info("AdGuard Home API found at %s", candidate)
                    return candidate
                if r.status_code == 401:
                    return candidate  # right path, wrong credentials — let it fail with 401
            except Exception:
                pass
        return None

    def _fetch_stats(self, host, auth):
        session = get_http_session()

        # Try /control prefix first (direct access), then without (reverse proxy setups)
        base = self._detect_base(session, host, auth)
        if base is None:
            return None, f"API not found at {host}/control or {host} — check URL and credentials"

        try:
            # Status: protection enabled, version
            status_resp = session.get(f"{base}/status", auth=auth, timeout=10, verify=False)
            status_resp.raise_for_status()
            status = status_resp.json()

            # Stats: queries, blocked, top clients, history
            stats_resp = session.get(f"{base}/stats", auth=auth, timeout=10, verify=False)
            stats_resp.raise_for_status()
            stats = stats_resp.json()

            # Filtering: rule count
            rules_count = 0
            try:
                filtering_resp = session.get(f"{base}/filtering/status", auth=auth, timeout=10, verify=False)
                filtering_resp.raise_for_status()
                rules_count = filtering_resp.json().get("rules_count", 0)
            except Exception as e:
                logger.warning("Could not fetch filtering status: %s", e)

        except Exception as e:
            logger.error("AdGuard Home fetch failed: %s", e)
            return None, str(e)

        total = stats.get("num_dns_queries", 0)
        blocked = stats.get("num_blocked_filtering", 0)
        safe_browsing = stats.get("num_replaced_safebrowsing", 0)
        safe_search = stats.get("num_replaced_safesearch", 0)
        parental = stats.get("num_replaced_parental", 0)
        avg_ms = round(stats.get("avg_processing_time", 0) * 1000, 2)

        blocked_percent = round((blocked / total * 100), 1) if total > 0 else 0.0

        # Top clients: list of {name, count}
        top_clients_raw = stats.get("top_clients", [])
        top_clients = []
        for entry in top_clients_raw[:5]:
            if isinstance(entry, dict):
                for name, count in entry.items():
                    top_clients.append({"name": name, "count": count})
                    break

        # 24h history arrays (one value per hour, oldest first)
        dns_history = stats.get("dns_queries", [])
        blocked_history = stats.get("blocked_filtering", [])

        # Normalise lengths for the chart
        chart_len = max(len(dns_history), len(blocked_history), 1)
        dns_history = dns_history[-24:] if len(dns_history) >= 24 else dns_history
        blocked_history = blocked_history[-24:] if len(blocked_history) >= 24 else blocked_history

        # Bar heights as percentages (relative to max bar)
        max_val = max(max(dns_history, default=0), 1)
        chart_bars = []
        for i in range(len(dns_history)):
            total_h = dns_history[i]
            block_h = blocked_history[i] if i < len(blocked_history) else 0
            chart_bars.append({
                "total_pct": round(total_h / max_val * 100),
                "blocked_pct": round(block_h / max_val * 100),
            })

        return {
            "protection_enabled": status.get("protection_enabled", False),
            "version": status.get("version", ""),
            "total_queries": total,
            "blocked_queries": blocked,
            "blocked_percent": blocked_percent,
            "safe_browsing": safe_browsing,
            "safe_search": safe_search,
            "parental": parental,
            "avg_processing_ms": avg_ms,
            "top_clients": top_clients,
            "rules_count": rules_count,
            "dns_queries_history": dns_history,
            "blocked_history": blocked_history,
            "chart_bars": chart_bars,
        }, None
