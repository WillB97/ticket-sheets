"""
Extract functions.

Generate new columns from existing data.
These functions modify the dataframe in place.
"""

from collections import defaultdict
from typing import Dict, List

import pandas as pd

from .internal import categorise_presents, update_tickets


def extract_tickets(data: pd.DataFrame, col_name: str) -> None:
    """
    Extract the tickets from the "Price categories" field.

    This function adds a column for each ticket type, with the quantity of that ticket.
    Generates columns in the format: "ticket_<ticket name>"
    """

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
    ticket_data.fillna(0, inplace=True)
    ticket_data = ticket_data.astype("Int64")

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

        # Special handling for under 1 year olds
        age = {"0": "U1"}.get(age, age)
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


def include_additional_adults(data: pd.DataFrame, col_name: str, ticket_type="Adult") -> None:
    """
    Add additional adults to the accompanying adult field, remove them from quantity.

    Also uses the "Price categories", "Quantity_formatted" and "Product title" fields.
    """
    # Skip if we don't have the Price categories field
    if "Price categories" not in data.columns:
        return

    # Only run on the products containing "Additional"
    input_data = data[data["Product title"].str.contains("Additional", regex=False)].copy()

    # Parse the price categories field to get a dict of ticket names and quantities
    # This will be run on the whole dataframe later, once accompanying adults have been added
    extract_tickets(input_data, "Price categories")

    ticket_col = f"ticket_{ticket_type}"

    # Add the selected ticket type to the col_name field
    if ticket_col in input_data.columns:
        data[col_name] = data[col_name].add(input_data[ticket_col], fill_value=0)

        # Remove the selected ticket type from the quantity field
        if "Quantity_formatted" in data.columns:
            data["Quantity_formatted"] = data["Quantity_formatted"].subtract(
                input_data[ticket_col], fill_value=0
            )


def include_additional_seniors(data: pd.DataFrame, col_name: str) -> None:
    """
    Add additional seniors to the accompanying senior field, remove them from quantity.

    Also uses the "Price categories", "Quantity_formatted" and "Product title" fields.
    """
    include_additional_adults(data, col_name, ticket_type="Senior")


def include_accompanying(
    data: pd.DataFrame,
    col_name: str,
    adult_col: str = "Accompanying Adult_formatted",
    senior_col: str = "Accompanying Senior_formatted",
) -> None:
    """Add accompanying adult and senior to the price categories field."""

    def add_accompanying(row: pd.Series, col_name: str) -> str:
        """Add accompanying adult and senior to the price categories field."""
        ticket_lines = row[col_name].splitlines()

        if adult_col in row.index:
            extra_adults = row[adult_col]
            if extra_adults != 0:
                # Update col_name with new price categories with extra adults added
                update_tickets(ticket_lines, "Adult", extra_adults)

        if senior_col in row.index:
            extra_seniors = row[senior_col]
            if extra_seniors != 0:
                # Update col_name with new price categories with extra seniors added
                update_tickets(ticket_lines, "Senior", extra_seniors)

        return "\n".join(ticket_lines)

    data[col_name] = data.apply(add_accompanying, axis="columns", args=(col_name,))


def split_infant_presents(
    data: pd.DataFrame, col_name: str, present_col: str = "Present Type_formatted"
) -> None:
    """Split infant present into separate infant ticket in price categories."""

    def split_infant_present(row: pd.Series, category_col: str, present_col: str) -> str:
        """Split infant present into separate infant ticket in price categories."""
        # Use present details to determine the split of child/infant tickets
        _present_counts = categorise_presents(row, present_col)

        ticket_lines = row[category_col].splitlines()
        # Update col_name with new price categories containing child & infant tickets
        update_tickets(ticket_lines, "Child", _present_counts["child_count"])
        if _present_counts["infant_count"] != 0:
            update_tickets(ticket_lines, "Infant", _present_counts["infant_count"])

        return "\n".join(ticket_lines)

    if present_col not in data.columns:
        # Skip if we don't have the Present Type field
        return

    data[col_name] = data.apply(
        split_infant_present, axis="columns", args=(col_name, present_col)
    )
