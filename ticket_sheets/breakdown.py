"""Generates summary statistics from the pre-processed dataframe."""

from typing import Dict, NamedTuple, Optional, Tuple

import pandas as pd
from flask import Markup

# TODO present breakdowns


class ExtraStats(NamedTuple):
    """Extra statistics for the ticket data."""

    max_price_order: str
    max_price: float
    max_price_tickets: Dict[str, int]
    max_price_ticket_makeup: str
    average_value: float
    average_tickets: Dict[str, float]
    average_ticket_makeup: str


class Totals(NamedTuple):
    """Grand totals for the ticket data."""

    tickets: Dict[str, int]
    num_tickets: int
    total_value: float
    num_orders: int
    online_value: float
    walkin_value: float = 0.0
    extra_stats: Optional[ExtraStats] = None


class EventTotal(NamedTuple):
    """Totals for a specific event."""

    tickets: Dict[str, int]
    num_tickets: int
    total_value: float
    num_orders: int


def generate_overall_breakdown(data: pd.DataFrame) -> Totals:
    """Generate the grand totals and extra statistics."""
    ticket_cols = [col for col in data.columns if col.startswith("ticket_")]

    if not ticket_cols:
        # extract_tickets needs to be in the input format
        raise RuntimeError("No ticket columns found")

    ticket_totals = data[ticket_cols].sum(axis="index").to_dict()
    # Remove the ticket_ prefix from the column names
    ticket_totals = {ticket.lstrip("ticket_"): qty for ticket, qty in ticket_totals.items()}
    ticket_totals = _sort_tickets(ticket_totals)

    if "Product price_formatted" in data.columns:
        # Extract the value to a python float
        total_value = data["Product price_formatted"].sum(axis="index").item()
    else:
        total_value = 0.0

    return Totals(
        tickets=ticket_totals,
        num_tickets=sum(ticket_totals.values()),
        total_value=total_value,
        num_orders=len(data),
        online_value=total_value,  # TODO
        walkin_value=0.0,
        extra_stats=generate_extra_stats(data),
    )


def generate_extra_stats(data: pd.DataFrame) -> ExtraStats:
    """Generate the extra statistics."""
    ticket_cols = [col for col in data.columns if col.startswith("ticket_")]

    if not ticket_cols:
        # extract_tickets needs to be in the input format
        raise RuntimeError("No ticket columns found")

    # Averages
    ticket_avgs = data[ticket_cols].mean(axis="index").to_dict()
    # Remove the ticket_ prefix from the column names
    ticket_avgs = {ticket.lstrip("ticket_"): qty for ticket, qty in ticket_avgs.items()}
    ticket_avgs = _sort_tickets(ticket_avgs)
    avg_makeup = [f"<b>{name[0]}</b>: {qty:.4f}" for name, qty in ticket_avgs.items()]

    if "Product price_formatted" in data.columns:
        # Extract the value to a python float
        avg_value = data["Product price_formatted"].mean(axis="index").item()
    else:
        avg_value = 0.0

    # Most expensive order
    if "Product price_formatted" in data.columns:
        max_order = data.sort_values(
            "Product price_formatted", ignore_index=True, ascending=False
        ).iloc[0]

        max_order_num = max_order["Order ID"]
        max_order_value = max_order["Product price_formatted"].item()
        max_order_ticket_cols = max_order[ticket_cols].to_dict()

        # Remove the ticket_ prefix from the column names
        max_order_tickets = {
            ticket.lstrip("ticket_"): qty for ticket, qty in max_order_ticket_cols.items()
        }
        max_order_tickets = _sort_tickets(max_order_tickets)
        max_makeup = [
            f"<b>{name[0]}</b>: {qty:.0f}" for name, qty in max_order_tickets.items()
        ]
    else:
        max_order_num = "-"
        max_order_value = 0.0
        max_order_tickets = {}
        max_makeup = "-"

    return ExtraStats(
        max_price_order=max_order_num,
        max_price=max_order_value,
        max_price_tickets=max_order_tickets,
        max_price_ticket_makeup=Markup(", ".join(max_makeup)),
        average_value=avg_value,
        average_tickets=ticket_avgs,
        average_ticket_makeup=Markup(", ".join(avg_makeup)),
    )


def generate_event_breakdown(data: pd.DataFrame) -> Dict[Tuple[str, str], EventTotal]:
    """
    Generate the totals for each event.

    The key is a tuple of (date, event).
    """
    event_totals = {}

    ticket_cols = [col for col in data.columns if col.startswith("ticket_")]
    if not ticket_cols:
        # extract_tickets needs to be in the input format
        raise RuntimeError("No ticket columns found")

    # Group by date and event
    for (date_grp, event_grp), event_data in data.groupby([
        data["Start date_formatted"].dt.date,
        "Product title_formatted",
    ]):
        ticket_totals = event_data[ticket_cols].sum(axis="index").to_dict()
        # Remove the ticket_ prefix from the column names
        ticket_totals = {
            ticket.lstrip("ticket_"): qty for ticket, qty in ticket_totals.items()
        }
        ticket_totals = _sort_tickets(ticket_totals)

        if "Product price_formatted" in event_data.columns:
            # Extract the value to a python float
            total_value = event_data["Product price_formatted"].sum(axis="index").item()
        else:
            total_value = 0.0

        date_str = date_grp.strftime("%d/%m/%y")

        event_totals[(date_str, event_grp)] = EventTotal(
            tickets=ticket_totals,
            num_tickets=sum(ticket_totals.values()),
            total_value=total_value,
            num_orders=len(event_data),
        )

    return event_totals


def _sort_tickets(tickets: Dict[str, int]) -> Dict[str, int]:
    """Sort the standard tickets."""
    ticket_order = {"Adult": 1, "Senior": 2, "Child": 3, "Infant": 4}

    ticket_list = list(tickets.items())
    ticket_list.sort(key=lambda x: ticket_order.get(x[0], 5))

    return dict(ticket_list)
