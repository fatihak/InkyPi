from dataclasses import dataclass


@dataclass
class DisplayConfig:
    """Everything needed to fetch and render one weather snapshot.

    Defaults mirror the current InkyPi weather plugin instance in
    src/config/device.json (Sittard, NL / OpenMeteo / metric).
    """
    latitude: float = 51.0004365
    longitude: float = 5.8993687
    units: str = "metric"          # "metric" | "imperial" | "standard"
    timezone: str = "Europe/Amsterdam"
    time_format: str = "24h"       # "24h" | "12h"
    forecast_days: int = 7
    graph_icon_step: int = 2
    show_moon_phase: bool = False
    background_color: str = "#fff8e5"
    text_color: str = "#000000"
    inky_saturation: float = 0.5
    refresh_interval_seconds: int = 600
