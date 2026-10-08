"""
Utility functions for parsing.
"""
from app.utils.numeri_italiani import parse_importo_ita


def safe_float(value, default=0.0):
    """Safely convert value to float (formato italiano incluso)."""
    return parse_importo_ita(value, default=default, keep_sign=True)


def safe_int(value, default=0):
    """Safely convert value to int."""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default
