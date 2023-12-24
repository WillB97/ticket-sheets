"""Provides functions for managing the global configuration."""

import json
from copy import deepcopy
from os import urandom
from typing import Dict, List, NamedTuple, Optional, Tuple

CONFIG_FILE = "config.json"
_config: Dict[str, any] = {}


def get_config():
    """
    Get the current configuration.

    Returns a reference to the global configuration object.
    """
    if _config == {}:
        _load_config()
    return _config


def update_config(**kwargs):
    """Update the configuration with the given values."""
    _config.update(kwargs)
    _save_config()


def refresh_config():
    """Refreshes the configuration by loading the latest configuration data."""
    print("Refreshing config")
    _load_config()


def _load_config():
    """
    Load the configuration from the config file.

    secret_key is generated if it does not exist.
    """
    with open(CONFIG_FILE, "r") as f:
        _config.clear()
        _config.update(json.load(f))

    # Set defaults if they don't exist
    _config["product filter"] = _config.get("product filter", "")
    _config["ticket prices"] = _config.get("ticket prices", {})
    _config["CSV URL"] = _config.get("CSV URL", "")
    _config["hide old orders"] = _config.get("hide old orders", False)
    _config["old order date"] = _config.get("old order date", "2021-01-01")

    # TODO load data config
    _config["data_config"] = DEFAULT_CONFIG

    if _config.get("secret_key") is None:
        _config["secret_key"] = urandom(24).hex()
        _save_config()


def _save_config():
    """Store the configuration in the config file."""
    # Remove the data config from the config file as it is not JSON serializable
    config = deepcopy(_config)
    _ = config.pop("data_config", None)

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


class ColumnConfig(NamedTuple):
    """The configuration for a column in the output table."""

    title: str
    input_column: Optional[str]
    align: str = "center"
    formatter: str = ""


class FieldConfig(NamedTuple):
    """The configuration for a column in the output data."""

    conversion: str = ""
    extractions: Tuple[str] = tuple()


class SortConfig(NamedTuple):
    """The configuration to sort an input data field by."""

    column: str
    reverse: bool = False


class TableConfig(NamedTuple):
    """The configuration for the output table."""

    columns: List[ColumnConfig]
    sorts: List[SortConfig]
    date_grp_col: Optional[str] = None
    demark_train: bool = False


class DataConfig(NamedTuple):
    """The configuration for the data pipeline."""

    input_format: Dict[str, FieldConfig]
    ticket_config: TableConfig
    alpha_config: TableConfig


DEFAULT_CONFIG = DataConfig(
    input_format={
        # Start date is automatically converted to a datetime
        # "Start date": FieldConfig(conversion="parse_date"),
        "Product Title": FieldConfig(conversion="simplify_product"),
        "Quantity": FieldConfig(conversion="parse_int"),
        "Product price": FieldConfig(conversion="tidy_price"),
    },
    ticket_config=TableConfig(
        columns=[
            ColumnConfig("Order", "Order ID"),
            ColumnConfig("Booking", "Booking ID"),
            ColumnConfig("Train", "Start date_formatted", formatter="train_time"),
            ColumnConfig(
                "First name", "Customer first name", align="right", formatter="title_case"
            ),
            ColumnConfig(
                "Last name", "Customer last name", align="left", formatter="title_case"
            ),
            ColumnConfig("Qty.", "Quantity"),
            ColumnConfig("Issued", None),
            ColumnConfig("Infants", None),
            ColumnConfig("Paid", "Product price_formatted", formatter="format_price"),
            ColumnConfig(
                "Price categories",
                "Price categories",
                align="left",
                formatter="insert_html_newlines",
            ),
            ColumnConfig("Notes", "Special Needs"),
        ],
        sorts=[
            SortConfig("Booking ID"),
            SortConfig("Order ID"),
            SortConfig("Start date_formatted"),
        ],
        date_grp_col="Start date_formatted",
        demark_train=True,
    ),
    alpha_config=TableConfig(
        columns=[
            ColumnConfig("Order", "Order ID"),
            ColumnConfig("Booking", "Booking ID"),
            ColumnConfig("Date", "Start date_formatted", formatter="train_date"),
            ColumnConfig("Train", "Start date_formatted", formatter="train_time"),
            ColumnConfig(
                "First name", "Customer first name", align="right", formatter="title_case"
            ),
            ColumnConfig(
                "Last name", "Customer last name", align="left", formatter="title_case"
            ),
            ColumnConfig("Qty.", "Quantity"),
            ColumnConfig("Paid", "Product price_formatted", formatter="format_price"),
            ColumnConfig(
                "Price categories",
                "Price categories",
                align="left",
                formatter="insert_html_newlines",
            ),
            ColumnConfig("Notes", "Special Needs"),
        ],
        sorts=[SortConfig("Customer first name"), SortConfig("Customer last name")],
        date_grp_col=None,
        demark_train=False,
    ),
)


SANTA_CONFIG = DataConfig(
    input_format={
        # Start date is automatically converted to a datetime
        # "Start date": FieldConfig(conversion="parse_date"),
        "Product Title": FieldConfig(conversion="simplify_product"),
        "Quantity": FieldConfig(conversion="parse_int"),
        # "Accompanying Adult": FieldConfig(),
        # "Accompanying Senior": FieldConfig(),
        "Product price": FieldConfig(conversion="tidy_price"),
        # "Present Type": FieldConfig(extractions=["extract_present_details"]),
    },
    ticket_config=TableConfig(
        columns=[
            ColumnConfig("Order", "Order ID"),
            ColumnConfig("Booking", "Booking ID"),
            ColumnConfig("Train", "Start date_formatted", formatter="train_time"),
            ColumnConfig(
                "First name", "Customer first name", align="right", formatter="title_case"
            ),
            ColumnConfig(
                "Last name", "Customer last name", align="left", formatter="title_case"
            ),
            ColumnConfig("Adults", "Accompanying Adult"),
            ColumnConfig("Seniors", "Accompanying Senior"),
            ColumnConfig("Grotto<br>passes", "Quantity"),
            ColumnConfig("Paid", "Product price_formatted", formatter="format_price"),
            ColumnConfig(
                "Presents", "Present Type_formatted", align="left", formatter="comma_sep"
            ),
            ColumnConfig("Notes", "Special Needs"),
        ],
        sorts=[
            SortConfig("Booking ID"),
            SortConfig("Order ID"),
            SortConfig("Start date_formatted"),
        ],
        date_grp_col="Start date_formatted",
        demark_train=True,
    ),
    alpha_config=TableConfig(
        columns=[
            ColumnConfig("Order", "Order ID"),
            ColumnConfig("Booking", "Booking ID"),
            ColumnConfig("Date", "Start date_formatted", formatter="train_date"),
            ColumnConfig("Train", "Start date_formatted", formatter="train_time"),
            ColumnConfig(
                "First name", "Customer first name", align="right", formatter="title_case"
            ),
            ColumnConfig(
                "Last name", "Customer last name", align="left", formatter="title_case"
            ),
            ColumnConfig("Adults", "Accompanying Adult"),
            ColumnConfig("Seniors", "Accompanying Senior"),
            ColumnConfig("Grotto<br>passes", "Quantity"),
            ColumnConfig("Paid", "Product price_formatted", formatter="format_price"),
            ColumnConfig(
                "Presents", "Present Type_formatted", align="left", formatter="comma_sep"
            ),
            ColumnConfig("Notes", "Special Needs"),
        ],
        sorts=[SortConfig("Customer first name"), SortConfig("Customer last name")],
        date_grp_col=None,
        demark_train=False,
    ),
)
