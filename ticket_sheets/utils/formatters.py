"""
Format functions.

These functions take the value of a field and produce a formatted string.
"""

from datetime import datetime
from typing import List, Optional

import pandas as pd
from flask import Markup


def title_case(value: str, booking: Optional[pd.Series] = None) -> str:
    """Convert the value to title case."""
    return value.title()


def comma_sep(value: List[str], booking: Optional[pd.Series] = None) -> str:
    """Convert the value to a comma separated string."""
    return ", ".join(value)


def train_time(value: datetime, booking: Optional[pd.Series] = None) -> str:
    """Extract the time from the datetime."""
    return value.strftime("%H:%M")


def train_date(value: datetime, booking: Optional[pd.Series] = None) -> str:
    """Extract the date from the datetime."""
    return value.strftime("%d/%m")


def format_price(value: float, booking: Optional[pd.Series] = None) -> str:
    """Format the value as a price."""
    return f"{value:.2f}"


def simple_date(value: datetime, booking: Optional[pd.Series] = None) -> str:
    """Shorten date to fit in the table."""
    return value.strftime("%a %d/%m")


def heading_date(value: datetime, booking: Optional[pd.Series] = None) -> str:
    """
    Format for the date headings.

    i.e. "SATURDAY NOVEMBER 30TH"
    """

    def date_suffix(day: int) -> str:
        if 10 <= day <= 13:
            return "th"
        else:
            return {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")

    return f"{value:%A %B %-d}{date_suffix(value.day)}".upper()


def insert_html_newlines(value: str, booking: Optional[pd.Series] = None) -> str:
    """Insert HTML line breaks into the value."""
    return Markup(value.replace("\n", "<br>"))
