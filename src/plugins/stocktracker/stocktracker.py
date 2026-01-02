#!/usr/bin/env python3

"""

Stock Tracker Plugin for InkyPi

This file should be saved as: src/plugins/stocktracker/stocktracker.py

"""

from plugins.base_plugin.base_plugin import BasePlugin

import yfinance as yf

import matplotlib.pyplot as plt

from datetime import datetime

import numpy as np

from PIL import Image

import io

class StockTracker(BasePlugin):

	"""Stock portfolio tracker plugin for InkyPi"""

	def generate_image(self, settings, device_config):

		"""Generate stock portfolio dashboard"""

		# Parse tickers and shares from settings
		try:
			tickers_str = settings.get('tickers', '').strip()
			shares_str = settings.get('shares', '').strip()
			period = settings.get('period', '1mo')

			if not tickers_str or not shares_str:
				raise RuntimeError("Please provide both tickers and shares")

			# Parse comma-separated values
			tickers = [t.strip().upper() for t in tickers_str.split(',')]
			shares = [float(s.strip()) for s in shares_str.split(',')]

			if len(tickers) != len(shares):
				raise RuntimeError("Number of tickers and shares must match")

		except ValueError as e:
			raise RuntimeError(f"Invalid input format: {str(e)}")

		# Fetch stock data
		stock_data = []

		for ticker, share_count in zip(tickers, shares):
			try:
				stock = yf.Ticker(ticker)
				hist = stock.history(period=period)
				info = stock.info

				if hist.empty:
					continue

				current_price = hist['Close'].iloc[-1]
				prev_price = hist['Close'].iloc[0]
				change = current_price - prev_price
				change_percent = (change / prev_price) * 100 if prev_price != 0 else 0

				stock_data.append({
					'symbol': ticker,
					'name': info.get('shortName', ticker),
					'price': current_price,
					'change': change,
					'change_percent': change_percent,
					'shares': share_count,
					'total_value': current_price * share_count,
					'total_change': change * share_count,
					'history': hist
				})

			except Exception as e:
				raise RuntimeError(f"Error fetching {ticker}: {str(e)}")

		if not stock_data:
			raise RuntimeError("No valid stock data retrieved")

		# Create dashboard
		return self._create_dashboard(stock_data)

	def _create_dashboard(self, stock_data):

		"""Create portfolio dashboard image"""

		fig, ax = plt.subplots(figsize=(16, 9.6), dpi=100)

		fig.patch.set_facecolor('#0f172a')

		# Calculate portfolio totals
		total_value = sum(data['total_value'] for data in stock_data)
		total_change = sum(data['total_change'] for data in stock_data)
		total_change_percent = (total_change / (total_value - total_change) * 100) if (total_value - total_change) != 0 else 0

		ax.set_facecolor('#0f172a')
		ax.axis('off')

		# Title
		ax.text(0.05, 0.95, 'Portfolio Dashboard',
			fontsize=32, fontweight='bold', color='white',
			transform=ax.transAxes)

		# Total Value
		change_color = '#10b981' if total_change >= 0 else '#ef4444'
		change_symbol = '▲' if total_change >= 0 else '▼'

		ax.text(0.05, 0.80, 'Total Value',
			fontsize=14, color='#94a3b8',
			transform=ax.transAxes)

		ax.text(0.05, 0.70, f'${total_value:,.2f}',
			fontsize=28, fontweight='bold', color='white',
			transform=ax.transAxes)

		# Change indicator
		ax.text(0.05, 0.58, f'{change_symbol} ${abs(total_change):,.2f} ({total_change_percent:+.2f}%)',
			fontsize=18, fontweight='bold', color=change_color,
			transform=ax.transAxes)

		# Holdings list header
		ax.text(0.05, 0.48, 'Holdings',
			fontsize=16, fontweight='bold', color='white',
			transform=ax.transAxes)

		# Holdings list
		y_pos = 0.42

		for data in stock_data:
			pct_of_portfolio = (data['total_value'] / total_value) * 100
			color = '#10b981' if data['change'] >= 0 else '#ef4444'

			# Ticker symbol
			ax.text(0.05, y_pos, f"{data['symbol']}",
				fontsize=12, color='white', fontweight='bold',
				transform=ax.transAxes)

			# Shares and price
			ax.text(0.25, y_pos, f"{data['shares']} @ ${data['price']:.2f}",
				fontsize=10, color='#94a3b8',
				transform=ax.transAxes)

			# Total value
			ax.text(0.50, y_pos, f"${data['total_value']:,.0f}",
				fontsize=11, color='white', fontweight='bold',
				transform=ax.transAxes)

			# Percentage and change
			ax.text(0.75, y_pos, f"{pct_of_portfolio:.1f}% {data['change_percent']:+.1f}%",
				fontsize=10, color=color,
				transform=ax.transAxes)

			y_pos -= 0.08

		# Save to PIL Image
		buf = io.BytesIO()
		plt.savefig(buf, format='png', facecolor='#0f172a', bbox_inches='tight', dpi=100)
		buf.seek(0)
		plt.close(fig)

		# Convert to PIL Image
		img = Image.open(buf)
		return img

	def generate_settings_template(self):

		"""Generate template variables for settings form"""

		template_params = super().generate_settings_template()

		template_params['period_options'] = [
			('1d', '1 Day'),
			('5d', '5 Days'),
			('1mo', '1 Month'),
			('3mo', '3 Months'),
			('6mo', '6 Months'),
			('1y', '1 Year'),
			('ytd', 'Year to Date')
		]

		# Ensure settings dict is included in template params
		if 'settings' not in template_params:
			template_params['settings'] = {}

		return template_params
