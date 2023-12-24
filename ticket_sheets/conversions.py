"""
Functions to extract values from the raw CSV data.

These include functions to extract the date and time, and to simplify the product names.
"""

import re
from datetime import datetime
from typing import List

import pandas as pd
from flask import Markup


# Conversion functions
# These functions take the value of a field and convert it to a different format
def simplify_product(value: str, booking: pd.Series) -> str:
    """Shorten product names to fit in the table."""
    value = value.replace("Weekend", "w/e")
    value = value.replace("- Day Ticket", "")
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
    return int(value)


# Format functions
# These functions take the value of a field and produce a formatted string
def title_case(value: str) -> str:
    """Convert the value to title case."""
    return value.title()


def comma_sep(value: List[str]) -> str:
    """Convert the value to a comma separated string."""
    return ", ".join(value)


def train_time(value: datetime) -> str:
    """Extract the time from the datetime."""
    return value.strftime("%H:%M")


def train_date(value: datetime) -> str:
    """Extract the date from the datetime."""
    return value.strftime("%d/%m")


def format_price(value: float) -> str:
    """Format the value as a price."""
    return f"{value:.2f}"


def simple_date(value: datetime) -> str:
    """Shorten date to fit in the table."""
    return value.strftime("%a %d/%m")


def heading_date(value: datetime) -> str:
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


def insert_html_newlines(value: str) -> str:
    """Insert HTML line breaks into the value."""
    return Markup(value.replace("\n", "<br>"))
