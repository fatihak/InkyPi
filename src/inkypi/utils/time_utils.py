import logging

logger = logging.getLogger(__name__)


def calculate_seconds(interval, unit):
    seconds = 5 * 60  # default to five minutes
    if unit == "minute":
        seconds = interval * 60
    elif unit == "hour":
        seconds = interval * 60 * 60
    elif unit == "day":
        seconds = interval * 60 * 60 * 24
    else:
        logger.warning(f"Unrecognized unit: {unit}, defaulting to 5 minutes")
    return seconds
