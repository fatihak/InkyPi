#!/usr/bin/env python3

"""
Stock Tracker Plugin for InkyPi - Enhanced Dashboard

This file should be saved as: src/plugins/stocktracker/stocktracker.py
"""

from plugins.base_plugin.base_plugin import BasePlugin

import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import datetime, timedelta
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
				data = self._fetch_stock_data(ticker, share_count, period)
				if data:
					stock_data.append(data)
			except Exception as e:
				raise RuntimeError(f"Error fetching {ticker}: {str(e)}")

		if not stock_data:
			raise RuntimeError("No valid stock data retrieved")

		# Create dashboard
		return self._create_dashboard(stock_data)

	def _fetch_stock_data(self, ticker, shares, period):

		"""Fetch stock data using yfinance"""

		stock = yf.Ticker(ticker)
		hist = stock.history(period=period)
		info = stock.info

		if hist.empty:
			return None

		current_price = hist['Close'].iloc[-1]
		prev_price = hist['Close'].iloc[0]
		change = current_price - prev_price
		change_percent = (change / prev_price) * 100 if prev_price != 0 else 0

		return {
			'symbol': ticker,
			'name': info.get('shortName', ticker),
			'price': current_price,
			'change': change,
			'change_percent': change_percent,
			'shares': shares,
			'total_value': current_price * shares,
			'total_change': change * shares,
			'history': hist
		}

	def _create_portfolio_chart(self, ax, stock_data):

		"""Create portfolio value chart over time"""

		ax.set_facecolor('#1e293b')

		# Calculate portfolio value over time
		dates = stock_data[0]['history'].index
		portfolio_values = []

		for date in dates:
			daily_value = 0
			for data in stock_data:
				if date in data['history'].index:
					price = data['history'].loc[date, 'Close']
					daily_value += price * data['shares']
			portfolio_values.append(daily_value)

		portfolio_values = np.array(portfolio_values)

		# Calculate change for color
		total_change = portfolio_values[-1] - portfolio_values[0]
		line_color = '#10b981' if total_change >= 0 else '#ef4444'

		# Plot portfolio value
		ax.plot(dates, portfolio_values, color=line_color, linewidth=3)
		ax.fill_between(dates, portfolio_values, alpha=0.2, color=line_color)

		# Change indicator
		change_percent = (total_change / portfolio_values[0]) * 100
		change_symbol = '▲' if total_change >= 0 else '▼'
		ax.text(0.98, 0.82, f'{change_symbol} ${abs(total_change):,.2f} ({change_percent:+.2f}%)',
				fontsize=14, fontweight='bold', color=line_color,
				transform=ax.transAxes, va='top', ha='right')

		# Styling
		ax.spines['top'].set_visible(False)
		ax.spines['right'].set_visible(False)
		ax.spines['bottom'].set_color('#334155')
		ax.spines['left'].set_color('#334155')
		ax.tick_params(colors='#94a3b8', labelsize=9)
		ax.grid(True, alpha=0.15, color='#334155', linestyle='--')

		# Format axes
		ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'${x:,.0f}'))
		ax.set_xticklabels([])

		# Set y-axis limits with margin
		value_min = portfolio_values.min()
		value_max = portfolio_values.max()
		value_range = value_max - value_min
		margin = value_range * 0.15
		ax.set_ylim(value_min - margin, value_max + margin)

	def _create_portfolio_summary(self, ax, stock_data):

		"""Create portfolio summary section"""

		ax.set_facecolor('#1e293b')
		ax.axis('off')

		# Calculate portfolio totals
		total_value = sum(data['total_value'] for data in stock_data)
		total_change = sum(data['total_change'] for data in stock_data)
		total_change_percent = (total_change / (total_value - total_change)) * 100 if (total_value - total_change) != 0 else 0

		# Title
		ax.text(0.05, 0.85, 'Portfolio Summary',
				fontsize=20, fontweight='bold', color='white',
				transform=ax.transAxes)

		# Total Portfolio Value
		ax.text(0.05, 0.65, 'Total Value',
				fontsize=12, color='#94a3b8',
				transform=ax.transAxes)
		ax.text(0.05, 0.50, f'${total_value:,.2f}',
				fontsize=24, fontweight='bold', color='white',
				transform=ax.transAxes)

		# Total Change
		change_color = '#10b981' if total_change >= 0 else '#ef4444'
		change_symbol = '▲' if total_change >= 0 else '▼'
		ax.text(0.05, 0.30, f'{change_symbol} ${abs(total_change):,.2f} ({total_change_percent:+.2f}%)',
				fontsize=16, fontweight='bold', color=change_color,
				transform=ax.transAxes)

		# Holdings breakdown
		ax.text(0.55, 0.85, 'Holdings Breakdown',
				fontsize=14, fontweight='bold', color='white',
				transform=ax.transAxes)

		y_pos = 0.70
		for data in stock_data:
			pct_of_portfolio = (data['total_value'] / total_value) * 100
			color = '#10b981' if data['change'] >= 0 else '#ef4444'

			ax.text(0.55, y_pos, f"{data['symbol']}",
					fontsize=13, color='white', fontweight='bold',
					transform=ax.transAxes)
			ax.text(0.67, y_pos, f"{data['shares']} × ${data['price']:.2f}",
					fontsize=11, color='#94a3b8',
					transform=ax.transAxes)
			ax.text(0.85, y_pos, f"{pct_of_portfolio:.1f}%",
					fontsize=13, color=color, fontweight='bold',
					transform=ax.transAxes)

			y_pos -= 0.12

	def _create_dashboard(self, stock_data):

		"""Create a dashboard with stock information and charts"""

		fig = plt.figure(figsize=(18, 12))
		fig.patch.set_facecolor('#0f172a')

		# Sort by change_percent to get best and worst performers
		sorted_stocks = sorted(stock_data, key=lambda x: x['change_percent'], reverse=True)

		# Select top 2 and bottom 2 performers
		if len(sorted_stocks) >= 4:
			best_performers = sorted_stocks[:2]
			worst_performers = sorted_stocks[-2:]
			selected_stocks = best_performers + worst_performers
		else:
			selected_stocks = sorted_stocks

		# Create stock cards
		for idx, data in enumerate(selected_stocks):
			if data is None:
				continue

			# Position: 0,1 = left column (best), 2,3 = right column (worst)
			if idx < 2:
				col = 0
				row = idx
			else:
				col = 1
				row = idx - 2

			# Card position with spacing
			card_height = 0.22
			card_width = 0.42
			left = 0.05 + col * 0.48
			bottom = 0.70 - row * 0.26

			# Stock info card
			ax_card = fig.add_axes([left, bottom, card_width, card_height * 0.35])
			ax_card.set_facecolor('#1e293b')
			ax_card.axis('off')

			# Stock symbol and name
			ax_card.text(0.05, 0.88, data['symbol'],
						fontsize=18, fontweight='bold', color='white',
						transform=ax_card.transAxes)
			ax_card.text(0.05, 0.68, data['name'][:25],
						fontsize=9, color='#94a3b8',
						transform=ax_card.transAxes)

			# Price
			ax_card.text(0.05, 0.38, f"${data['price']:.2f}",
						fontsize=18, fontweight='bold', color='white',
						transform=ax_card.transAxes)

			# Change
			change_color = '#10b981' if data['change'] >= 0 else '#ef4444'
			change_symbol = '▲' if data['change'] >= 0 else '▼'
			change_text = f"{change_symbol} ${abs(data['change']):.2f} ({data['change_percent']:+.2f}%)"
			ax_card.text(0.05, 0.12, change_text,
						fontsize=13, fontweight='bold', color=change_color,
						transform=ax_card.transAxes)

			# Holdings info
			ax_card.text(0.95, 0.12, f"{data['shares']} shares = ${data['total_value']:,.2f}",
						fontsize=9, color='#64748b', ha='right',
						transform=ax_card.transAxes)

			# Mini chart
			ax_chart = fig.add_axes([left, bottom + card_height * 0.40, card_width, card_height * 0.58])
			ax_chart.set_facecolor('#1e293b')

			# Plot price history
			dates = data['history'].index
			prices = data['history']['Close'].values

			# Color based on overall trend
			line_color = '#10b981' if data['change'] >= 0 else '#ef4444'
			ax_chart.plot(dates, prices, color=line_color, linewidth=2.5)
			ax_chart.fill_between(dates, prices, alpha=0.2, color=line_color)

			# Styling
			ax_chart.spines['top'].set_visible(False)
			ax_chart.spines['right'].set_visible(False)
			ax_chart.spines['bottom'].set_color('#334155')
			ax_chart.spines['left'].set_color('#334155')
			ax_chart.tick_params(colors='#94a3b8', labelsize=8)
			ax_chart.grid(True, alpha=0.15, color='#334155', linestyle='--')

			# Hide x-axis labels
			ax_chart.set_xticklabels([])

			# Y-axis scaling with margin
			price_min = prices.min()
			price_max = prices.max()
			price_range = price_max - price_min
			margin = price_range * 0.15
			ax_chart.set_ylim(price_min - margin, price_max + margin)

			ax_chart.yaxis.set_major_locator(plt.MaxNLocator(5))
			for label in ax_chart.yaxis.get_ticklabels():
				label.set_fontsize(8)

		# Portfolio value chart
		portfolio_chart_ax = fig.add_axes([0.05, 0.28, 0.90, 0.14])
		self._create_portfolio_chart(portfolio_chart_ax, stock_data)

		# Portfolio Summary (showing ALL stocks)
		portfolio_ax = fig.add_axes([0.05, 0.05, 0.90, 0.20])
		self._create_portfolio_summary(portfolio_ax, stock_data)

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

		# Ensure settings dict is included
		if 'settings' not in template_params:
			template_params['settings'] = {}

		return template_params
