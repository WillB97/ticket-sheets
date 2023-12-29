"""Generates summary statistics from the pre-processed dataframe."""

from typing import Dict, List, NamedTuple, Optional, Tuple

import pandas as pd
from flask import Markup

from .utils.internal import sort_tickets

PRESENT_AGES = [
    "BU1",
    *[f"B{i}" for i in range(1, 15)],
    "GU1",
    *[f"G{i}" for i in range(1, 15)],
]


class ExtraStats(NamedTuple):
    """Extra statistics for the ticket data."""

    max_price_order: str
    max_price: float
    max_price_tickets: Dict[str, int]
    max_price_ticket_makeup: str
    average_value: float
    average_tickets: Dict[str, float]
    average_ticket_makeup: str
    max_presents: Optional[int] = None
    max_presents_order: Optional[str] = None


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


def generate_overall_breakdown(
    data: pd.DataFrame, presents_column: Optional[str] = None
) -> Totals:
    """Generate the grand totals and extra statistics."""
    ticket_cols = [col for col in data.columns if col.startswith("ticket_")]

    if not ticket_cols:
        # extract_tickets needs to be in the input format
        raise RuntimeError("No ticket columns found")

    ticket_totals = data[ticket_cols].sum(axis="index").to_dict()
    # Remove the ticket_ prefix from the column names
    ticket_totals = {ticket.lstrip("ticket_"): qty for ticket, qty in ticket_totals.items()}
    ticket_totals = sort_tickets(ticket_totals)

    total_value = 0.0
    online_value = 0.0
    walkin_value = 0.0
    if "Walk-in price" in data.columns:
        # Extract the value to a python float
        total_value = data["Walk-in price"].sum(axis="index").item()
        online_value = data["Product price_formatted"].sum(axis="index").item()
        walkin_value = total_value - online_value
    elif "Product price_formatted" in data.columns:
        # Extract the value to a python float
        total_value = data["Product price_formatted"].sum(axis="index").item()
        online_value = total_value

    return Totals(
        tickets=ticket_totals,
        num_tickets=sum(ticket_totals.values()),
        total_value=total_value,
        num_orders=len(data),
        online_value=online_value,
        walkin_value=walkin_value,
        extra_stats=generate_extra_stats(data, presents_column),
    )


def generate_extra_stats(
    data: pd.DataFrame, presents_column: Optional[str] = None
) -> ExtraStats:
    """Generate the extra statistics."""
    ticket_cols = [col for col in data.columns if col.startswith("ticket_")]

    if not ticket_cols:
        # extract_tickets needs to be in the input format
        raise RuntimeError("No ticket columns found")

    # Averages
    ticket_avgs = data[ticket_cols].mean(axis="index").to_dict()
    # Remove the ticket_ prefix from the column names
    ticket_avgs = {ticket.lstrip("ticket_"): qty for ticket, qty in ticket_avgs.items()}
    ticket_avgs = sort_tickets(ticket_avgs)
    avg_makeup = [f"<b>{name[0]}</b>: {qty:.4f}" for name, qty in ticket_avgs.items()]

    if "Walk-in price" in data.columns:
        # Extract the value to a python float
        avg_value = data["Walk-in price"].mean(axis="index").item()
    elif "Product price_formatted" in data.columns:
        # Extract the value to a python float
        avg_value = data["Product price_formatted"].mean(axis="index").item()
    else:
        avg_value = 0.0

    # Most expensive order
    if "Walk-in price" in data.columns or "Product price_formatted" in data.columns:
        if "Walk-in price" in data.columns:
            price_col = "Walk-in price"
        else:
            price_col = "Product price_formatted"

        max_order = data.sort_values(price_col, ignore_index=True, ascending=False).iloc[0]

        max_order_num = max_order["Order ID"]
        max_order_value = max_order[price_col].item()
        max_order_ticket_cols = max_order[ticket_cols].to_dict()

        # Remove the ticket_ prefix from the column names
        max_order_tickets = {
            ticket.lstrip("ticket_"): qty for ticket, qty in max_order_ticket_cols.items()
        }
        max_order_tickets = sort_tickets(max_order_tickets)
        max_makeup = [
            f"<b>{name[0]}</b>: {qty:.0f}" for name, qty in max_order_tickets.items()
        ]
    else:
        max_order_num = "-"
        max_order_value = 0.0
        max_order_tickets = {}
        max_makeup = "-"

    if presents_column is not None:
        max_presents_order, max_presents = get_max_presents(data, presents_column)
    else:
        max_presents_order = None
        max_presents = None

    return ExtraStats(
        max_price_order=max_order_num,
        max_price=max_order_value,
        max_price_tickets=max_order_tickets,
        max_price_ticket_makeup=Markup(", ".join(max_makeup)),
        average_value=avg_value,
        average_tickets=ticket_avgs,
        average_ticket_makeup=Markup(", ".join(avg_makeup)),
        max_presents=max_presents,
        max_presents_order=max_presents_order,
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

    data.sort_values("Start date_formatted", ignore_index=True, inplace=True)

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
        ticket_totals = sort_tickets(ticket_totals)

        if "Walk-in price" in event_data.columns:
            # Extract the value to a python float
            total_value = event_data["Walk-in price"].sum(axis="index").item()
        elif "Product price_formatted" in event_data.columns:
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


def summarise_presents_by_age(data: pd.DataFrame, col_name: str) -> pd.DataFrame:
    """Summarise the presents by age."""
    # Use explode to split the list of presents into separate rows
    present_ages = data[["Start date_formatted", col_name]].explode(col_name).dropna()
    present_ages.rename(
        columns={col_name: "age", "Start date_formatted": "date_time"}, inplace=True
    )
    present_ages.sort_values("date_time", ignore_index=True, inplace=True)

    present_ages["date"] = present_ages["date_time"].dt.date.astype("datetime64[ns]")

    # Count the number of presents for each age on each day
    present_ages = (
        present_ages[["date", "age"]]
        .groupby(["date", "age"])
        .size()
        .rename("count")
        .astype("Int64")
        .reset_index(drop=False)
    )

    # Pivot to get the ages as columns and the dates as rows
    present_table = present_ages.pivot(index="date", columns="age", values="count")

    # sort rows by date
    present_table.sort_index(inplace=True)

    # format the dates in the index
    present_table.index = present_table.index.strftime("%d/%m/%y")

    # fill in missing ages
    present_table = present_table.reindex(columns=PRESENT_AGES, fill_value=0)
    present_table.fillna(0, inplace=True)

    return present_table


def summarise_presents_by_train(
    data: pd.DataFrame, train_times: List[str], col_name: str
) -> pd.DataFrame:
    """Summarise the presents by train."""
    # count the number of presents for each booking
    present_counts = (
        pd.concat(
            [data["Start date_formatted"], data[col_name].apply(len)],
            names=["date_time", "present_count"],
            axis=1,
        )
        .rename(columns={"Start date_formatted": "date_time", col_name: "present_count"})
        .sort_values("date_time")
    )

    # group by date and train
    present_counts = present_counts.groupby("date_time").sum().reset_index(drop=False)

    present_counts["date"] = present_counts["date_time"].dt.date.astype("datetime64[ns]")
    present_counts["train"] = present_counts["date_time"].dt.time.apply(
        lambda x: x.strftime("%H:%M")
    )

    # pivot to get the train times as columns
    present_table = present_counts.pivot(index="date", columns="train", values="present_count")

    # sort rows by date
    present_table.sort_index(inplace=True)

    # format the dates in the index
    present_table.index = present_table.index.strftime("%d/%m/%y")

    # fill in missing train times
    present_table = present_table.reindex(columns=train_times, fill_value=0)
    present_table.fillna(0, inplace=True)

    return present_table


def get_max_presents(data: pd.DataFrame, col_name: str) -> Tuple[str, int]:
    """Get the maximum number of presents."""
    # count the number of presents for each booking
    present_counts = (
        pd.concat([data["Order ID"], data[col_name].apply(len)], axis=1)
        .rename(columns={col_name: "present_count"})
        .sort_values("present_count", ascending=False)
        .reset_index(drop=True)
    )

    # Select highest present count (due to the sort above, this will be the first row)
    max_presents = present_counts.iloc[0]

    return max_presents["Order ID"], max_presents["present_count"]
