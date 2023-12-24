"""
Functions to extract values from the raw CSV data.

These include functions to extract the date and time, and to simplify the product names.
"""

import re
from datetime import datetime
from typing import Dict, List, Tuple

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


# Extract functions
# These functions modify the dataframe in place
def extract_tickets(data: pd.DataFrame, col_name: str) -> None:
    """Extract the tickets from the "Price categories" field."""

    def extract_ticket(row: pd.Series, col_name) -> Dict[str, int]:
        """Extract the ticket name and quantity from a ticket string."""
        tickets = {}
        ticket: str = row[col_name]
        # Split each cell by newline
        ticket_fields = ticket.splitlines()

        for field in ticket_fields:
            # Split each line by colon, then whitespace
            ticket_name, ticket_qty_data = field.split(":")
            ticket_qty = int(ticket_qty_data.split()[0])

            # Create columns for each ticket type
            tickets[f"ticket_{ticket_name}"] = ticket_qty

        return tickets

    ticket_data = data.apply(
        extract_ticket, axis="columns", args=(col_name,), result_type="expand"
    )

    # Merge the ticket data into the dataframe
    data[ticket_data.columns] = ticket_data


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


# Total functions
# These functions take a list of values and produce a single value
# Return type is Tuple[return_value, colspan]
def sum(values: pd.Series) -> Tuple[float, int]:
    """Sum the values."""
    return values.sum(), 1


def price_sum(values: pd.Series) -> Tuple[str, int]:
    """Sum the values and format as a price."""
    return format_price(values.sum()), 1


def order_count(values: pd.Series, colspan: int = 1) -> Tuple[int, int]:
    """Count the number of orders."""
    return Markup(f"<b>Orders:</b> {len(values)}"), colspan


def label(values: pd.Series, colspan: int = 1) -> Tuple[str, int]:
    """Count the number of orders."""
    return Markup("<b>Totals</b>"), colspan


def category_sum(values: pd.Series) -> Tuple[int, int]:
    """Sum value of each category."""
    # Extract tickets from each row
    values_df = values.to_frame()
    extract_tickets(values_df, values.name)

    # Remove the original column
    values_df.drop(columns=[values.name], inplace=True)

    # Sum each category
    sum_df = values_df.sum(axis="index")

    # Format the totals
    totals = {col_name.lstrip("ticket_"): sum_df[col_name] for col_name in sum_df.index}

    # TODO: fix ordering
    totals_str = "<br>".join(
        f"{ticket_name}: {ticket_qty:.0f}" for ticket_name, ticket_qty in totals.items()
    )
    return Markup(totals_str), 1


def present_sum(values: pd.Series) -> Tuple[int, int]:
    """Sum the number of present tickets."""
    _values_df = values.to_frame()
    return "TODO", 1  # TODO


def order_count_2(values: pd.Series) -> Tuple[int, int]:
    """Count the number of orders, with colspan=2."""
    return order_count(values, 2)


def label_2(values: pd.Series) -> Tuple[str, int]:
    """Count the number of orders, with colspan=2."""
    return label(values, 2)


def label_3(values: pd.Series) -> Tuple[str, int]:
    """Count the number of orders, with colspan=3."""
    return label(values, 3)
