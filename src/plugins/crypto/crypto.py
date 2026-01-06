from plugins.base_plugin.base_plugin import BasePlugin
import requests
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

# CoinGecko API endpoints (free, no API key required)
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price"
COINGECKO_COIN_DATA_URL = "https://api.coingecko.com/api/v3/coins/{coin_id}"

# Supported cryptocurrencies
SUPPORTED_CRYPTOS = {
    'bitcoin': {'symbol': 'BTC', 'name': 'Bitcoin'},
    'ethereum': {'symbol': 'ETH', 'name': 'Ethereum'},
    'solana': {'symbol': 'SOL', 'name': 'Solana'},
    'dogecoin': {'symbol': 'DOGE', 'name': 'Dogecoin'},
}

# Supported fiat currencies
SUPPORTED_CURRENCIES = {
    'usd': {'symbol': '$', 'name': 'US Dollar'},
    'eur': {'symbol': '€', 'name': 'Euro'},
    'gbp': {'symbol': '£', 'name': 'British Pound'},
    'jpy': {'symbol': '¥', 'name': 'Japanese Yen'},
    'cny': {'symbol': '¥', 'name': 'Chinese Yuan'},
}

class Crypto(BasePlugin):
    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params['style_settings'] = True
        template_params['currencies'] = SUPPORTED_CURRENCIES
        template_params['cryptos'] = SUPPORTED_CRYPTOS
        return template_params

    def generate_image(self, settings, device_config):
        try:
            # Get settings
            currency = settings.get('currency', 'usd').lower()
            selected_cryptos = settings.get('selectedCryptos', ['bitcoin', 'ethereum', 'solana', 'dogecoin'])
            display_change = settings.get('displayChange', 'true') == 'true'
            refresh_time = settings.get('displayRefreshTime', 'true') == 'true'

            if currency not in SUPPORTED_CURRENCIES:
                currency = 'usd'

            # Fetch crypto data
            crypto_data = self.fetch_crypto_prices(selected_cryptos, currency, display_change)

            # Get timezone for last refresh time
            timezone_name = device_config.get_config("timezone", default="America/New_York")
            tz = pytz.timezone(timezone_name)
            current_time = datetime.now(tz)

            # Prepare template parameters
            dimensions = device_config.get_resolution()
            if device_config.get_config("orientation") == "vertical":
                dimensions = dimensions[::-1]

            template_params = {
                'crypto_data': crypto_data,
                'currency_symbol': SUPPORTED_CURRENCIES[currency]['symbol'],
                'currency': currency.upper(),
                'display_change': display_change,
                'display_refresh_time': refresh_time,
                'last_refresh_time': current_time.strftime("%b %d, %I:%M %p"),
                'plugin_settings': settings
            }

            # Render the image
            return self.render_image(
                dimensions,
                'crypto.html',
                'crypto.css',
                template_params
            )

        except Exception as e:
            logger.error(f"Crypto image generation failed: {str(e)}")
            raise

    def fetch_crypto_prices(self, crypto_ids, currency, include_change=True):
        """Fetch cryptocurrency prices from CoinGecko API"""
        try:
            # Build API parameters
            ids = ','.join(crypto_ids)
            params = {
                'ids': ids,
                'vs_currencies': currency,
            }

            if include_change:
                params['include_24hr_change'] = 'true'
                params['include_24hr_vol'] = 'true'

            # Make API request
            response = requests.get(COINGECKO_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Process the data
            crypto_list = []
            for crypto_id in crypto_ids:
                if crypto_id in data:
                    crypto_info = SUPPORTED_CRYPTOS.get(crypto_id, {})
                    price_data = data[crypto_id]

                    price = price_data.get(currency, 0)
                    change_24h = price_data.get(f'{currency}_24h_change', 0)

                    crypto_list.append({
                        'id': crypto_id,
                        'symbol': crypto_info.get('symbol', crypto_id.upper()),
                        'name': crypto_info.get('name', crypto_id.capitalize()),
                        'price': self.format_price(price),
                        'price_raw': price,
                        'change_24h': round(change_24h, 2) if change_24h else 0,
                        'change_direction': 'up' if change_24h > 0 else 'down' if change_24h < 0 else 'neutral'
                    })

            return crypto_list

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch crypto prices: {str(e)}")
            raise RuntimeError(f"Failed to fetch cryptocurrency data: {str(e)}")
        except Exception as e:
            logger.error(f"Error processing crypto data: {str(e)}")
            raise RuntimeError(f"Error processing cryptocurrency data: {str(e)}")

    def format_price(self, price):
        """Format price with appropriate decimal places"""
        if price >= 1000:
            return f"{price:,.2f}"
        elif price >= 1:
            return f"{price:.2f}"
        elif price >= 0.01:
            return f"{price:.4f}"
        else:
            return f"{price:.8f}"
