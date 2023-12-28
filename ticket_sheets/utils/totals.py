"""
Total functions.

These functions take a list of values and produce a single value.
Return type is Tuple[return_value, colspan]
"""

from typing import Tuple

import pandas as pd
from flask import Markup

from .extractions import extract_tickets
from .formatters import format_price
from .internal import categorise_presents


def sum(values: pd.Series) -> Tuple[str, int]:
    """Sum the values."""
    return Markup(f"<b>{values.sum()}</b>"), 1


def price_sum(values: pd.Series) -> Tuple[str, int]:
    """Sum the values and format as a price."""
    return Markup(f"<b>{format_price(values.sum())}</b>"), 1


def order_count(values: pd.Series, colspan: int = 1) -> Tuple[str, int]:
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
    values_df = values.to_frame()
    # Make child and infant counts
    count_df = values_df.apply(
        categorise_presents, axis="columns", args=(values.name,), result_type="expand"
    )

    # Sum counts
    sum_df = count_df.sum(axis="index")

    # Format as string
    totals_str = f"Child: {sum_df['child_count']}<br>Infant: {sum_df['infant_count']}"

    return Markup(totals_str), 1


def order_count_2(values: pd.Series) -> Tuple[int, int]:
    """Count the number of orders, with colspan=2."""
    return order_count(values, 2)


def label_2(values: pd.Series) -> Tuple[str, int]:
    """Count the number of orders, with colspan=2."""
    return label(values, 2)


def label_3(values: pd.Series) -> Tuple[str, int]:
    """Count the number of orders, with colspan=3."""
    return label(values, 3)
