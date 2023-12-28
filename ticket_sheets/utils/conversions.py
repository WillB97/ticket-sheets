"""
Conversion functions.

Functions to extract values from the raw CSV data.
These functions take the value of a field and convert it to a different format.
"""

import re
from datetime import datetime

import pandas as pd


def simplify_product(value: str, booking: pd.Series) -> str:
    """Shorten product names to fit in the table."""
    value = value.replace("Weekend", "w/e")
    value = value.replace("- Day Ticket", "")
    value = value.replace("Tickets", "")
    value = value.replace("Ticket", "")
    return value.strip()


def tidy_price(value: str, booking: pd.Series) -> float:
    """Remove currency symbols from price and convert it to a float."""
    return float(value.replace("&pound;", "").replace("£", ""))


def parse_date(value: str, booking: pd.Series) -> datetime:
    """Parse the date string into a datetime object."""
    value_clean = re.sub(r"([0-9]+)(st|nd|rd|th)", r"\1", value).replace(",", "")
    return datetime.strptime(value_clean, "%A %B %d %Y %I:%M %p")


def parse_int(value: str, booking: pd.Series) -> int:
    """Parse the value into an integer."""
    try:
        return int(value)
    except ValueError:
        return 0
