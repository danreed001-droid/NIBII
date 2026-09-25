"""Flat-zone bands. band(h) = 0.5 * (sigma/100) * sqrt(h/252)."""
import math

TRADING_DAYS = 252
HORIZONS = (1, 5, 10)


def band(sigma: float, h: int) -> float:
    """Half-width of the flat zone for horizon h, rounded to 6 dp."""
    return round(0.5 * (sigma / 100.0) * math.sqrt(h / TRADING_DAYS), 6)


def daily_sigma(sigma: float) -> float:
    """Annualised vol (in points, e.g. VIX 15.67) -> one-day sigma as a fraction."""
    return (sigma / 100.0) / math.sqrt(TRADING_DAYS)


def flat_zone(close: float, b: float, ndigits: int = 4):
    return round(close * (1 - b), ndigits), round(close * (1 + b), ndigits)
