"""Generate the tally data for santa present tally sheets."""

from typing import Dict, List, Optional

import pandas as pd


def generate_tally_data(
    data: pd.DataFrame, col_name: str, day: int, month: int, needs_col: Optional[str] = None
) -> pd.DataFrame:
    """Generate the tally data for santa present tally sheets."""
    cols = ["Order ID", "Order ID_formatted", "Start date_formatted", col_name]
    if needs_col:
        cols.append(needs_col)
    present_data = data[cols].sort_values(by=["Order ID_formatted", "Start date_formatted"])

    # Filter to the relevant orders
    present_data = present_data[
        (present_data["Start date_formatted"].dt.day == day)
        & (present_data["Start date_formatted"].dt.month == month)
    ]

    # Count the number of presents in each order
    present_data["present_count"] = present_data[col_name].apply(len)

    # Remove orders with no presents
    present_data = present_data[(present_data["present_count"] > 0)]

    # Add a column of the train time
    present_data["train_time"] = present_data["Start date_formatted"].dt.time.apply(
        lambda x: x.strftime("%H:%M")
    )

    present_data.rename(
        columns={
            "Start date_formatted": "date_time",
            col_name: "presents",
            needs_col: "needs_codes",
        },
        inplace=True,
    )
    if needs_col is None:
        present_data["needs_codes"] = ""

    # Strip additional comments from the needs codes
    present_data["needs_codes"] = present_data["needs_codes"].str.split(":").str[0]

    return present_data


def render_tally_data(
    data: pd.DataFrame, train_limits: Dict[str, int]
) -> List[List[Dict[str, str]]]:
    """Render the tally data for santa present tally sheets."""

    def format_presents(row: pd.Series) -> Dict[str, str]:
        """Format a set of presents."""
        formatted = [
            {
                "present": present,
                "end_family": False,
                # This is set later
                "train_limit": False,
                "order_id": row["Order ID"],
                "needs_codes": row["needs_codes"],
            }
            for present in row["presents"]
        ]
        if formatted:
            formatted[-1]["end_family"] = True
        return formatted

    # Use apply to create arrays of the output fields
    data["present_formatted"] = data.apply(format_presents, axis="columns")

    # Use explode to expand the arrays into rows
    tally_df = data[["train_time", "present_formatted", "Order ID"]].explode(
        "present_formatted"
    )

    # Use groupby to number the presents on each train
    tally_df["present_num"] = tally_df.groupby("train_time").cumcount() + 1

    # Use pivot to create columns from the trains
    tally_table_df = tally_df.pivot(
        index="present_num", columns="train_time", values="present_formatted"
    )
    # fill in missing train times
    tally_table_df = tally_table_df.reindex(columns=list(train_limits.keys()))

    # add rows for the train limit
    max_train_limit = max(train_limits.values())
    num_rows = max(max_train_limit + 1, 26)
    tally_table_df = tally_table_df.reindex(range(1, num_rows + 1))

    default_cell_value = {
        "present": "",
        "end_family": False,
        "train_limit": False,
        "order_id": "",
        "needs_codes": "",
    }
    # fill in missing cells
    tally_table_df = tally_table_df.applymap(
        lambda x: default_cell_value.copy() if pd.isna(x) else x
    )

    # add train limit
    for train, limit in train_limits.items():
        tally_table_df.loc[limit, train]["train_limit"] = True

    # Use to_dict to convert the dataframe to a list of dicts
    tally_data = tally_table_df.to_dict(orient="split")

    return tally_data["data"], tally_data["columns"]
