"""
Functions to extract values from the raw CSV data.

These include functions to extract the date and time, and to simplify the product names.
"""

import re
from collections import defaultdict
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
    try:
        return int(value)
    except ValueError:
        return 0


# Extract functions
# These functions modify the dataframe in place
def extract_tickets(data: pd.DataFrame, col_name: str) -> None:
    """Extract the tickets from the "Price categories" field."""

    def extract_ticket(row: pd.Series, col_name: str) -> Dict[str, int]:
        """Extract the ticket name and quantity from a ticket string."""
        tickets = defaultdict(int)
        ticket: str = row[col_name]
        # Split each cell by newline
        ticket_fields = ticket.splitlines()

        for field in ticket_fields:
            # Split each line by colon, then whitespace
            ticket_name, ticket_qty_data = field.split(":")
            ticket_qty = int(ticket_qty_data.split()[0])

            # Create columns for each ticket type
            tickets[f"ticket_{ticket_name}"] += ticket_qty

        return dict(tickets)

    ticket_data = data.apply(
        extract_ticket, axis="columns", args=(col_name,), result_type="expand"
    )

    # Merge the ticket data into the dataframe
    data[ticket_data.columns] = ticket_data


def extract_present_details(data: pd.DataFrame, col_name: str) -> None:
    """
    Generate arrays of present ages and genders.

    Also takes in ages from the "Child Age *" fields.
    """

    def format_present(row: pd.Series) -> str:
        """Format the present value."""
        gender_char = {"Boy": "B", "Girl": "G"}.get(row["gender"], "?")

        # Take the age number at the start of the string
        age = row["age"].split()[0]

        # Special handling for 0/1 year olds
        age = {"0": "U1", "1": "U2"}.get(age, age)
        return f"{gender_char}{age}"

    def present_details(row: pd.Series, col_name: str) -> List[str]:
        """Reorganise the supplied present values into a list of age and gender."""
        # Short-circuit if there are no present values
        if row[col_name] == "":
            return []

        # This column is in the format: "#1: Boy"
        # The age columns are in the format: "#1: 7 yrs old" or "#1: 1 to 2 yrs old"
        gender_data = pd.DataFrame(
            (
                (num.strip("#"), gender_str.strip())
                for gender in row[col_name].splitlines()
                for num, gender_str in [gender.split(":")]
            ),
            columns=["number", "gender"],
        ).set_index("number")

        age_columns = filter(lambda col: col.startswith("Child Age"), row.index)
        age_data = pd.DataFrame(
            (
                # Generate a single list of age values from the age columns
                (num.strip("#"), age_str.strip())
                for age_col in age_columns
                for age_val in row[age_col].splitlines()
                for num, age_str in [age_val.split(":")]
            ),
            columns=["number", "age"],
        ).set_index("number")

        # Merge gender and age data
        present_data = gender_data.join(age_data, how="left", validate="one_to_one")
        present_data["age"].fillna("Choose", inplace=True)

        # Format each value
        return present_data.apply(format_present, axis="columns").tolist()

    data[f"{col_name}_formatted"] = data.apply(
        present_details, axis="columns", args=(col_name,)
    )


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

    def categorise_presents(row: pd.Series, col_name: str) -> Dict[str, int]:
        """Count the number of children and infants."""
        presents: List[str] = row[col_name]
        # infant presents start with 'BU' or 'GU', child presents start with 'B' or 'G'
        infant_presents = list(
            filter(lambda present: len(present) == 3 and present[1] == "U", presents)
        )
        child_presents = list(filter(lambda present: present not in infant_presents, presents))

        return {"child_count": len(child_presents), "infant_count": len(infant_presents)}

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
