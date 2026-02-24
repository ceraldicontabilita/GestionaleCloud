"""
Utility functions for parsing.
"""

class ParsingError(Exception):
    """Custom exception for parsing errors."""
    pass


def safe_float(value, default=0.0):
    """Safely convert value to float."""
    if value is None:
        return default
    try:
        if isinstance(value, str):
            # Handle Italian number format (1.234,56 -> 1234.56)
            value = value.strip().replace('€', '').replace(' ', '')
            if ',' in value and '.' in value:
                value = value.replace('.', '').replace(',', '.')
            elif ',' in value:
                value = value.replace(',', '.')
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    """Safely convert value to int."""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default
