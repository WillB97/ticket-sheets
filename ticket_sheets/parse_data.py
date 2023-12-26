"""
Process the pandas dataframe of bookings using configurations for the output table.

Generates a table of the bookings to be output and the summary statistics.
"""

from datetime import datetime
from typing import Callable, Dict, List, NamedTuple

import pandas as pd
from flask import Markup

from ticket_sheets import conversions

from .config import FieldConfig, TableConfig


class TableRow(NamedTuple):
    """A wrapper of the row in the output table."""

    booking_type: str
    booking: Dict[str, str]


# Load functions
def parse_csv(filename: str) -> pd.DataFrame:
    """
    Load the CSV file into a pandas dataframe.

    This function is used to load the CSV file into a pandas dataframe.
    """
    data = pd.read_csv(filename, dtype="string", keep_default_na=False)
    # Pre-emptively parse the date column
    data["Start date_formatted"] = data["Start date"].apply(conversions.parse_date, args=({},))

    return data


# Filter functions
def apply_filters(data: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Apply the filters to the data."""
    data = filter_old_orders(data, config["hide old orders"], config["old order date"])
    data = filter_product(data, config["product filter"])

    return data


def filter_old_orders(data: pd.DataFrame, hide_old: bool, old_order_date: str) -> pd.DataFrame:
    """Optionally filters the data to bookings that are after the specified date."""
    if not hide_old:
        return data

    return data[data["Start date_formatted"] >= datetime.fromisoformat(old_order_date)].copy()


def filter_product(data: pd.DataFrame, product_filter: str) -> pd.DataFrame:
    """
    Filter the data by product name.

    Filters the data to bookings that contain the substring in the product name.
    """
    if product_filter == "":
        return data

    return data[
        data["Product title"].str.contains(product_filter, case=False, regex=False)
    ].copy()


# Parse functions
def get_dates(data: pd.DataFrame) -> List[str]:
    """
    Extract the dates contained in the data.

    This function returns the unique set of dates that the data covers.
    """
    unique_dates_arr = data["Start date_formatted"].dt.date.unique()
    unique_dates = unique_dates_arr.tolist()
    unique_dates.sort()

    return [f"{date_val:%d/%m}" for date_val in unique_dates]


def conversion_wrapper(
    row: pd.Series, conv_func: Callable[[str, pd.Series], any], col: str
) -> any:
    """Wrapper function to apply a conversion function to a row."""
    return conv_func(row[col], row)


def parse_bookings(data: pd.DataFrame, config: Dict[str, FieldConfig]) -> pd.DataFrame:
    """
    Parse the bookings from the data.

    This function extracts processable values from the data and adds them to the
    dataframe using the configuration provided.
    """
    # Iterate over each column in data and apply conversion if it exists
    for col_name in data.columns:
        if (col_config := config.get(col_name)) is not None:
            if conv_name := col_config.conversion:
                try:
                    conv_func = getattr(conversions, conv_name)
                except AttributeError:
                    raise ValueError(f"Invalid conversion name {conv_name}")
                # Pass full row to conversion function
                data.loc[:, f"{col_name}_formatted"] = data.apply(
                    conversion_wrapper, args=(conv_func, col_name), axis="columns"
                )
            for extract_name in col_config.extractions:
                try:
                    extract_func = getattr(conversions, extract_name)
                except AttributeError:
                    raise ValueError(f"Invalid extraction name {extract_name}")
                # Extraction functions modify the dataframe in place
                extract_func(data, col_name)

    return data


# Format functions
def format_for_table(
    data: pd.DataFrame, config: TableConfig, daily_totals: bool = False
) -> List[TableRow]:
    """
    Format the data for the output table.

    Adds day totals and creates the row structures for the output table.
    """
    # sort by each column in config.sorts
    for sort_config in config.sorts:
        try:
            if data[sort_config.column].dtype == "string":
                # Sort strings case-insensitively
                def sort_func(x):
                    return x.str.lower()
            else:
                sort_func = None

            data.sort_values(
                sort_config.column,
                ascending=not sort_config.reverse,
                key=sort_func,
                inplace=True,
                ignore_index=True,
                kind="stable",
            )
        except KeyError:
            # Skip sorts by absent columns
            continue

    output_rows = []
    # group by date
    if config.group_by_date:
        for date_val, date_group in data.groupby(data["Start date_formatted"].dt.date):
            # If group by date, before each group, add date entry
            output_rows.append(TableRow("date", {"date": conversions.heading_date(date_val)}))

            for _, time_group in date_group.groupby(data["Start date_formatted"].dt.time):
                # Add each group to list
                for _, row in time_group.iterrows():
                    output_rows.append(TableRow("booking", format_row(row, config)))

                if config.demark_train:
                    # If demark train, after each group, add divider
                    output_rows.append(TableRow("divider", {}))

            # If day totals, after each group, add day totals
            if daily_totals:
                # Avoid having a divider before the day totals
                if output_rows[-1].booking_type == "divider":
                    _ = output_rows.pop()

                output_rows.append(TableRow("totals", format_total_row(date_group, config)))
                output_rows.append(TableRow("divider", {}))
    else:
        for _, row in data.iterrows():
            output_rows.append(TableRow("booking", format_row(row, config)))

    return output_rows


def format_row(row: pd.Series, config: TableConfig) -> Dict[str, str]:
    """
    Format a row of the output table.

    This function formats a row of the output table using the configuration
    provided.
    """
    output_row = {}

    # Extract output values from row using config.columns
    for col_config in config.columns:
        col_title = col_config.title
        if "<br>" in col_title:
            col_title = Markup(col_title)

        if col_config.input_column is None:
            output_row[col_title] = ""
        else:
            raw_value = row[col_config.input_column]
            # Apply formatting to output values
            if col_config.formatter:
                try:
                    format_func = getattr(conversions, col_config.formatter)
                except AttributeError:
                    raise ValueError(f"Invalid format name {col_config.formatter}")
                value = format_func(raw_value)
            else:
                value = raw_value
            output_row[col_title] = value

    return output_row


def format_total_row(day_data: pd.DataFrame, config: TableConfig) -> Dict[str, str]:
    """
    Calculate the totals for a day and format them for the output table.

    This function formats a totals row for the output table using the configuration
    provided.
    """
    output_row = {}

    # Generate output values for each column in config.columns
    for col_config in config.columns:
        col_title = col_config.title
        if "<br>" in col_title:
            col_title = Markup(col_title)

        if col_config.input_column is None or col_config.total_method == "":
            output_row[col_title] = "", 1
        else:
            col_values = day_data[col_config.input_column]
            # Apply total method to output values
            try:
                total_func = getattr(conversions, col_config.total_method)
            except AttributeError:
                raise ValueError(f"Invalid total method name {col_config.total_method}")

            value = total_func(col_values)
            output_row[col_title] = value

    return output_row
