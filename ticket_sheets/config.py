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


def update_prices(filter: str, prices: Optional[Dict[str, float]]):
    """Update the ticket prices for the given filter."""
    if prices is None:
        # Remove the filter if the prices are None
        _ = _config["ticket prices"].pop(filter, None)
    else:
        _config["ticket prices"][filter] = prices
    _save_config()


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

    # Load the data configs and set the active config
    _load_data_configs()

    if _config.get("secret_key") is None:
        _config["secret_key"] = urandom(24).hex()
        _save_config()


def _save_config():
    """Store the configuration in the config file."""
    # Remove the data config from the config file as it is not JSON serializable
    config = deepcopy(_config)
    _ = config.pop("data_config", None)

    # Convert the data configs to dicts for serialization
    _store_data_configs(config)

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


def _load_data_configs():
    """Load the data config structures from the config file."""

    def load_table_config(config_root):
        return TableConfig(
            columns=[
                ColumnConfig(**column_config) for column_config in config_root["columns"]
            ],
            sorts=[SortConfig(**sort_config) for sort_config in config_root["sorts"]],
            group_by_date=config_root.get("group_by_date", False),
            demark_train=config_root.get("demark_train", False),
        )

    if _config.get("data_configs_dict") is None or len(_config["data_configs_dict"]) == 0:
        _config["data_configs_dict"] = _store_data_configs({"data_configs": DEFAULT_CONFIGS})
        _config["active_config"] = "general"

    # Take configs as dicts from data_configs_dict and store them in data_configs
    _config["data_configs"] = {
        name: DataConfig(
            input_format={
                field: FieldConfig(**field_config)
                for field, field_config in sorted(
                    # Guarantee the order of the fields
                    config["input_format"].items(),
                    key=lambda x: x[1]["order"],
                )
            },
            ticket_config=load_table_config(config["ticket_config"]),
            alpha_config=load_table_config(config["alpha_config"]),
            train_limits=config["train_limits"],
            presents_column=config.get("presents_column"),
            needs_column=config.get("needs_column"),
        )
        for name, config in _config["data_configs_dict"].items()
    }

    if _config.get("data_config") is None:
        try:
            _config["data_config"] = _config["data_configs"][_config["active_config"]]
        except KeyError:
            _config["active_config"] = "general"

            if "general" not in _config["data_configs"]:
                _config["data_configs"]["general"] = DEFAULT_CONFIGS["general"]

            _config["data_config"] = _config["data_configs"]["general"]


def _store_data_configs(config):
    """Store the data config structures as dicts in the config file."""

    def store_table_config(table_config):
        return {
            "columns": [
                dict(column_config._asdict()) for column_config in table_config.columns
            ],
            "sorts": [dict(sort_config._asdict()) for sort_config in table_config.sorts],
            "group_by_date": table_config.group_by_date,
            "demark_train": table_config.demark_train,
        }

    config["data_configs_dict"] = {
        name: {
            "input_format": {
                # Set the order of the fields for serialization
                field: {**field_config._asdict(), "order": order}
                for order, (field, field_config) in enumerate(data_config.input_format.items())
            },
            "ticket_config": store_table_config(data_config.ticket_config),
            "alpha_config": store_table_config(data_config.alpha_config),
            "train_limits": data_config.train_limits,
            "presents_column": data_config.presents_column,
            "needs_column": data_config.needs_column,
        }
        for name, data_config in config["data_configs"].items()
    }

    # Remove the data config from the config file as it is not properly serialized
    _ = config.pop("data_configs", None)
    _ = config.pop("data_config", None)

    return config["data_configs_dict"]


def activate_config(name: str):
    """Activate the named configuration."""
    if name not in _config["data_configs"]:
        raise ValueError(f"Invalid config name {name}")
    _config["active_config"] = name
    _config["data_config"] = _config["data_configs"][name]
    _save_config()


class ColumnConfig(NamedTuple):
    """The configuration for a column in the output table."""

    title: str
    input_column: Optional[str]
    align: str = "center"
    formatter: str = ""
    total_method: str = ""


class FieldConfig(NamedTuple):
    """The configuration for a column in the output data."""

    conversion: str = ""
    extractions: Tuple[str] = tuple()
    order: int = -1


class SortConfig(NamedTuple):
    """The configuration to sort an input data field by."""

    column: str
    reverse: bool = False


class TableConfig(NamedTuple):
    """The configuration for the output table."""

    columns: List[ColumnConfig]
    sorts: List[SortConfig]
    group_by_date: bool = False
    demark_train: bool = False


class DataConfig(NamedTuple):
    """The configuration for the data pipeline."""

    input_format: Dict[str, FieldConfig]
    ticket_config: TableConfig
    alpha_config: TableConfig
    train_limits: Dict[str, int]
    presents_column: Optional[str] = None
    needs_column: Optional[str] = None


DEFAULT_CONFIGS = {
    "general": DataConfig(
        input_format={
            # Start date is automatically converted to a datetime
            # "Start date": FieldConfig(conversion="parse_date"),
            "Booking ID": FieldConfig(conversion="parse_int"),
            "Order ID": FieldConfig(conversion="parse_int"),
            "Product title": FieldConfig(conversion="simplify_product"),
            "Quantity": FieldConfig(conversion="parse_int"),
            "Product price": FieldConfig(conversion="tidy_price"),
            # Needed for breakdown
            "Price categories": FieldConfig(extractions=["extract_tickets"]),
        },
        ticket_config=TableConfig(
            columns=[
                ColumnConfig("Order", "Order ID", total_method="label_3"),
                ColumnConfig("Booking", "Booking ID"),
                ColumnConfig("Train", "Start date_formatted", formatter="train_time"),
                ColumnConfig(
                    "First name",
                    "Customer first name",
                    align="right",
                    formatter="title_case",
                    total_method="order_count_2",
                ),
                ColumnConfig(
                    "Last name", "Customer last name", align="left", formatter="title_case"
                ),
                ColumnConfig("Qty.", "Quantity_formatted", total_method="sum"),
                ColumnConfig("Issued", None),
                ColumnConfig("Infants", None),
                ColumnConfig(
                    "Paid",
                    "Product price_formatted",
                    formatter="format_price",
                    total_method="price_sum",
                ),
                ColumnConfig(
                    "Price categories",
                    "Price categories",
                    align="left",
                    formatter="insert_html_newlines",
                    total_method="category_sum",
                ),
                ColumnConfig("Notes", "Special Needs"),
            ],
            sorts=[
                SortConfig("Booking ID_formatted"),
                SortConfig("Order ID_formatted"),
                SortConfig("Start date_formatted"),
            ],
            group_by_date=True,
            demark_train=False,
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
                ColumnConfig("Qty.", "Quantity_formatted"),
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
            group_by_date=False,
            demark_train=False,
        ),
        train_limits={},
    ),
    "santa": DataConfig(
        input_format={
            # Start date is automatically converted to a datetime
            # "Start date": FieldConfig(conversion="parse_date"),
            "Booking ID": FieldConfig(conversion="parse_int"),
            "Order ID": FieldConfig(conversion="parse_int"),
            "Product title": FieldConfig(conversion="simplify_product"),
            "Quantity": FieldConfig(conversion="parse_int"),
            # Must occur after Quantity
            "Accompanying Adult": FieldConfig(
                conversion="parse_int", extractions=["include_additional_adults"]
            ),
            "Accompanying Senior": FieldConfig(
                conversion="parse_int", extractions=["include_additional_seniors"]
            ),
            "Present Type": FieldConfig(extractions=["extract_present_details"]),
            # Needed for breakdown, must occur after Accompanying Adult and Accompanying Senior
            "Price categories": FieldConfig(
                extractions=[
                    "include_accompanying",
                    "split_infant_presents",
                    "extract_tickets",
                ]
            ),
            # Must occur after Accompanying Adult, Senior and Price categories
            "Product price": FieldConfig(
                conversion="tidy_price", extractions=["calculate_walkin_price"]
            ),
        },
        ticket_config=TableConfig(
            columns=[
                ColumnConfig("Order", "Order ID", total_method="label_3"),
                ColumnConfig("Booking", "Booking ID"),
                ColumnConfig("Train", "Start date_formatted", formatter="train_time"),
                ColumnConfig(
                    "First name",
                    "Customer first name",
                    align="right",
                    formatter="title_case",
                    total_method="order_count_2",
                ),
                ColumnConfig(
                    "Last name", "Customer last name", align="left", formatter="title_case"
                ),
                ColumnConfig("Adults", "Accompanying Adult_formatted", total_method="sum"),
                ColumnConfig("Seniors", "Accompanying Senior_formatted", total_method="sum"),
                ColumnConfig("Grotto<br>passes", "Quantity_formatted", total_method="sum"),
                ColumnConfig(
                    "Paid",
                    "Walk-in price",
                    formatter="format_walkin_price",
                    total_method="price_sum",
                ),
                ColumnConfig(
                    "Presents",
                    "Present Type_formatted",
                    align="left",
                    formatter="comma_sep",
                    total_method="present_sum",
                ),
                ColumnConfig("Notes", "Special Needs"),
            ],
            sorts=[
                SortConfig("Booking ID_formatted"),
                SortConfig("Order ID_formatted"),
                SortConfig("Start date_formatted"),
            ],
            group_by_date=True,
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
                ColumnConfig("Adults", "Accompanying Adult_formatted"),
                ColumnConfig("Seniors", "Accompanying Senior_formatted"),
                ColumnConfig("Grotto<br>passes", "Quantity_formatted"),
                ColumnConfig("Paid", "Walk-in price", formatter="format_walkin_price"),
                ColumnConfig(
                    "Presents", "Present Type_formatted", align="left", formatter="comma_sep"
                ),
                ColumnConfig("Notes", "Special Needs"),
            ],
            sorts=[SortConfig("Customer first name"), SortConfig("Customer last name")],
            group_by_date=False,
            demark_train=False,
        ),
        train_limits={
            "10:30": 15,
            "11:00": 20,
            "11:30": 20,
            "12:00": 20,
            "12:30": 15,
            "13:30": 20,
            "14:00": 20,
            "14:30": 20,
            "15:00": 20,
            "15:30": 20,
            "16:00": 10,
        },
        presents_column="Present Type_formatted",
        needs_column="Special Needs",
    ),
}
