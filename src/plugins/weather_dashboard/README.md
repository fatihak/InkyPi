# Weather Dashboard Plugin

A comprehensive dashboard plugin that combines weather forecast, birthdays, and countdown information on a single display.

## Features

### Layout
- **Left Half (50%)**: Weather information
  - Current weather with icon, temperature, and "feels like"
  - 6 compact metrics (Sunrise, Sunset, Wind, Humidity, UV Index, Air Quality)
  - 3-day forecast with high/low temps and precipitation probability

- **Right Half (50%)**: Split into two sections
  - **Top Quarter**: Current week number and upcoming birthdays (next 30 days)
  - **Bottom Quarter**: Countdown to a specific date/event

## Metrics Included

The plugin displays **6 essential weather metrics** (optimized for space):
1. **Sunrise** - Time of sunrise
2. **Sunset** - Time of sunset
3. **Wind** - Wind speed
4. **Humidity** - Relative humidity percentage
5. **UV Index** - UV radiation index
6. **Air Quality** - Air quality index with quality scale

**Excluded metrics** (to save space):
- Visibility
- Air Pressure

> If you need these metrics, you can modify the `parse_compact_metrics()` method in `weather_dashboard.py`

## Weather Data Sources

The plugin supports two weather providers:

### 1. Open-Meteo (Default - Free, No API Key Required)
- No registration needed
- Free for non-commercial use
- Provides all essential weather data

### 2. OpenWeatherMap (Optional - Requires API Key)
- Requires free API key from [OpenWeatherMap](https://openweathermap.org/api)
- Provides additional data points
- Store API key in `.env` file as `OPEN_WEATHER_MAP_SECRET`

## Configuration

### Weather Settings
1. **Location**: Click "Select Location" to choose coordinates on a map
2. **Weather Provider**: Choose between OpenWeatherMap or Open-Meteo
3. **Units**: Select Imperial (°F), Metric (°C), or Standard (K)
4. **Title**: Display location name (OpenWeatherMap only) or custom title

### Birthday Settings
1. **CSV File Path**: **Absolute path** to your birthday CSV file
   - ⚠️ **IMPORTANT**: Use absolute paths like `/home/username/birthdays.csv`
   - ❌ Do NOT use `~/birthdays.csv` - the tilde (~) expands to `/root/` since InkyPi runs as root
   - ✅ Example: `/home/lumpidu/birthdays.csv`
   - See `birthdays_example.csv` for format

### Birthday CSV Format
Create a CSV file with two columns: `name` and `date`

```csv
name,date
John Doe,1990-05-15
Jane Smith,03-20
Bob Johnson,12-25
```

**Date formats supported:**
- Full date with year: `YYYY-MM-DD` (e.g., `1990-05-15`) - **Shows age!**
- Month and day only: `MM-DD` (e.g., `03-20`) - No age displayed

The plugin will:
- Show only birthdays within the next 30 days
- Display up to 5 upcoming birthdays
- Sort by proximity to current date
- **Calculate and display age when birth year is provided**

Example display:
```
🎂 John Doe (35)    Today!
🎂 Jane Smith       Tomorrow
```

### Countdown Settings
1. **Countdown Title**: Name of the event (e.g., "Vacation", "Wedding", "Conference")
2. **Countdown Date**: Target date in YYYY-MM-DD format
3. **Countdown Image** (Optional): Path to an image file to display with the countdown
   - Example: `/home/user/vacation.jpg`
   - Image is displayed in 16:9 aspect ratio
   - Leave empty for text-only countdown

The countdown displays:
- Number of days remaining (or days passed if date has passed)
- Event name
- Optional custom image (16:9 aspect ratio)
- Target date (when no image is provided)

## Installation

The plugin is already installed in `/home/user/InkyPi/src/plugins/weather_dashboard/`

To activate it:
1. Restart the InkyPi service:
   ```bash
   sudo systemctl restart inkypi.service
   ```

2. Access the InkyPi web interface and add "Weather Dashboard" to your playlist

## File Structure

```
weather_dashboard/
├── weather_dashboard.py      # Main plugin code
├── plugin-info.json           # Plugin metadata
├── icon.png                   # Plugin icon
├── settings.html              # Configuration form
├── birthdays_example.csv      # Example birthday CSV
├── README.md                  # This file
└── render/
    ├── weather_dashboard.html # HTML template
    └── weather_dashboard.css  # Stylesheet
```

## Customization

### Adjusting Metrics
To add/remove metrics, edit the `parse_compact_metrics()` method in `weather_dashboard.py`:

```python
def parse_compact_metrics(self, weather, air_quality, tz, units, time_format, icon_dir):
    data_points = []

    # Add your custom metrics here
    data_points.append({
        "label": "Your Label",
        "measurement": value,
        "unit": "unit",
        "icon": path_to_icon
    })

    return data_points
```

### Adjusting Layout
Edit `render/weather_dashboard.css` to change:
- Grid proportions (currently 50/50 split)
- Font sizes
- Spacing and padding
- Colors and borders

### Adjusting Number of Forecast Days
Currently set to 3 days. To change, modify line 123 in `weather_dashboard.py`:
```python
template_params['forecast'] = template_params['forecast'][:4]  # Current day + 3 forecast
```

### Adjusting Birthday Display Count
Currently shows up to 5 upcoming birthdays within 30 days. To change, modify line 172 in `weather_dashboard.py`:
```python
return birthdays[:5]  # Change this number
```

And line 163 to change the time window:
```python
if days_until <= 30:  # Change this number of days
```

## Responsive Design & Orientation

The plugin automatically adapts to both orientations:
- **Landscape/Panorama mode** (default): Weather on left (50%), info on right (50%)
- **Portrait mode**: Weather on top (50%), info on bottom (50%)
- Different screen sizes using container queries and viewport units

### Changing Orientation

Orientation is set in the **InkyPi Web UI > Settings > Device Settings**:
1. Go to the InkyPi web interface
2. Navigate to Settings
3. Under "Device Settings", find "Orientation"
4. Select either "Horizontal" or "Vertical"
5. Save and refresh your display

The plugin will automatically adjust its layout based on the orientation setting.

## Troubleshooting

### Plugin doesn't appear
- Verify `plugin-info.json` exists
- Restart InkyPi service: `sudo systemctl restart inkypi.service`
- Check logs: `sudo journalctl -u inkypi.service -f`

### Weather data not loading
- Verify latitude/longitude are set
- If using OpenWeatherMap, verify API key in `.env` file
- Try switching to Open-Meteo (no API key required)

### Birthdays not showing
- Verify CSV file path is correct and file exists
- Check CSV format matches example (name,date)
- Ensure dates are within next 30 days
- Check file permissions (readable by InkyPi service)

### Countdown not showing
- Verify date is in YYYY-MM-DD format
- Ensure both title and date are filled

## Style Settings

The plugin supports InkyPi's standard style settings:
- Background color or image
- Text color
- Margins (top, bottom, left, right)
- Frame styles (None, Corner, Top and Bottom, Rectangle)

Access these in the plugin settings under "Style Settings"

## Credits

This plugin combines functionality from:
- InkyPi Weather plugin (weather data fetching)
- InkyPi Countdown plugin (countdown logic)
- Custom CSV parsing for birthdays

## License

Same as InkyPi (GPL 3.0)
