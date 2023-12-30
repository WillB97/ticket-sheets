#!/usr/bin/env python3
"""Ticket-sheets flask server."""

import csv
import json
from datetime import datetime
from io import StringIO

import pandas as pd
from flask import (
    Flask,
    Markup,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.exceptions import InternalServerError

from flask_session import Session

from ._version import __version__
from .breakdown import (
    PRESENT_AGES,
    generate_event_breakdown,
    generate_overall_breakdown,
    summarise_presents_by_age,
    summarise_presents_by_train,
)
from .config import DataConfig, get_config, refresh_config, update_config, update_prices
from .parse_data import apply_filters, format_for_table, get_dates, parse_bookings, parse_csv
from .tally import generate_tally_data, render_tally_data

app = Flask(__name__)
config = get_config()

app.config["SECRET_KEY"] = config["secret_key"]

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


def render_tickets_error(error, err_str=None):
    """Render the error page with the given error message."""
    return render_template(
        "error.html",
        config={
            "filter": config.get("product filter", ""),
            "hide_old": config.get("hide old orders", ""),
            "old_date": config.get("old order date", ""),
            "version": __version__,
        },
        error=error,
        error_string=err_str,
    )


@app.errorhandler(500)
def internal_server_error(e: InternalServerError):
    """Use the custom error page for unhandled exceptions."""
    orig_exception = e.original_exception
    return render_tickets_error(
        "Internal Server Error", f"{orig_exception.__class__.__name__}: {orig_exception}"
    )


@app.before_request
def load_fresh_config():
    """
    Load the config file before each request and check a CSV has been uploaded.

    Under gunicorn different instances will respond to requests
    so the loaded config may have been updated.
    """
    refresh_config()

    # Check if we have a CSV and go to the upload page if not
    # Skip for POST requests, /upload and static files
    if request.method == "POST":
        return
    if request.endpoint == "prepare_upload" or request.endpoint == "static":
        return

    try:
        orders = session["csv_data"]
    except KeyError:
        return render_tickets_error("Please upload a CSV")

    if orders.empty:
        return render_tickets_error("No Ticket Data Found")


@app.route("/")
@app.route("/upload", methods=["GET"])
def prepare_upload():
    """Render the upload page."""
    return render_template("upload.html", active="upload", **global_vars())


@app.route("/upload", methods=["POST"])
def uploaded_tickets():
    """
    Process the uploaded ticket data from a CSV file.

    Returns
    -------
        If the CSV file is successfully processed and contains data,
            it redirects to the ticket_table page.
        If the CSV file is empty, it displays an error message.
        If no file is uploaded or the uploaded file is not a CSV file,
            it displays an error message.
    """
    try:
        f = request.files["fileupload"]

        raw_df = parse_csv(f)

        if not raw_df.empty:
            session["csv_name"] = f.filename
            session["csv_data"] = raw_df
            session["csv_uploaded"] = datetime.now().strftime("%d-%b %H:%M")
            return redirect(url_for("ticket_table"))
        else:
            session["csv_data"] = None
            err_string = "No Ticket Data Found"
    except (KeyError, pd.errors.ParserError):
        err_string = "Please upload a CSV file"

    return render_template("upload.html", error=err_string, active="upload", **global_vars())


@app.route("/config-url", methods=["POST"])
def update_config_url():
    """
    Save the CSV URL to the config file.

    This means all pages and sessions will have the same CSV URL populated.
    """
    # store request data
    update_config(**{"CSV URL": request.form.get("csvUrl", "")})

    # return to the previous page
    return redirect(request.referrer)


@app.route("/config", methods=["POST"])
def update_config_values():
    """
    Save the filter values to the config file.

    This means all pages and sessions will use the same filter.
    """
    # store request data
    update_config(**{
        "product filter": request.form.get("filter", ""),
        "hide old orders": (request.form.get("hideOld", "") == "hide"),
        "old order date": request.form.get("filterDate", ""),
    })

    # return to the previous page
    return redirect(request.referrer)


@app.route("/tickets")
def ticket_table():
    """Render the ticket data as a table in date order."""
    data = session["csv_data"].copy()
    filtered_data = apply_filters(data, config)
    table_configs: DataConfig = config["data_config"]

    parsed_bookings = parse_bookings(
        filtered_data, table_configs.input_format, config["ticket prices"]
    )
    # Also include daily totals
    rendered_bookings = format_for_table(
        parsed_bookings, table_configs.ticket_config, daily_totals=True
    )

    header = [Markup(column.title) for column in table_configs.ticket_config.columns]
    column_align = {
        column.title: column.align for column in table_configs.ticket_config.columns
    }

    return render_template(
        "ticket_table.html",
        header=header,
        bookings=rendered_bookings,
        align=column_align,
        columns=len(header),
        demark_train=table_configs.ticket_config.demark_train,
        active="tickets",
        **global_vars(),
    )


@app.route("/alpha")
def alphabetical_orders():
    """Render the ticket data as a table in alphabetical order."""
    data = session["csv_data"].copy()
    filtered_data = apply_filters(data, config)
    table_configs: DataConfig = config["data_config"]

    parsed_bookings = parse_bookings(
        filtered_data, table_configs.input_format, config["ticket prices"]
    )
    rendered_bookings = format_for_table(parsed_bookings, table_configs.alpha_config)

    header = [Markup(column.title) for column in table_configs.alpha_config.columns]
    column_align = {
        column.title: column.align for column in table_configs.alpha_config.columns
    }

    return render_template(
        "ticket_table.html",
        header=header,
        bookings=rendered_bookings,
        align=column_align,
        columns=len(header),
        no_totals=True,
        show_filter=True,
        active="alpha",
        **global_vars(),
    )


@app.route("/csv-breakdown")
def csv_breakdown():
    """Render a summary of the ticket data as CSV."""
    data = session["csv_data"].copy()
    filtered_data = apply_filters(data, config)
    table_configs: DataConfig = config["data_config"]

    parsed_bookings = parse_bookings(
        filtered_data, table_configs.input_format, config["ticket prices"]
    )

    # (date, event) -> (tickets, num_tickets, total value, num orders)
    event_totals = generate_event_breakdown(parsed_bookings)

    # generate unique list of ticket types
    ticket_names = set(ticket for event in event_totals.values() for ticket in event[0].keys())

    csv_file = StringIO()
    csv_obj = csv.DictWriter(
        csv_file,
        fieldnames=["Date", "Event", "Tickets", "Orders", "Total Value", *ticket_names],
        restval=0,
    )
    csv_obj.writeheader()

    for (date, event), (tickets, num_tickets, total_value, num_orders) in event_totals.items():
        row = {
            "Date": date,
            "Event": event,
            "Tickets": num_tickets,
            "Orders": num_orders,
            "Total Value": total_value,
        }
        row.update(tickets)
        csv_obj.writerow(row)

    output = make_response(csv_file.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=event_breakdown_export.csv"
    output.headers["Content-type"] = "text/csv"
    return output


@app.route("/breakdown")
def ticket_breakdown():
    """Render a summary of the ticket data."""
    data = session["csv_data"].copy()
    filtered_data = apply_filters(data, config)
    table_configs: DataConfig = config["data_config"]

    parsed_bookings = parse_bookings(
        filtered_data, table_configs.input_format, config["ticket prices"]
    )

    # Calculate grand totals and extra statistics
    grand_totals = generate_overall_breakdown(
        parsed_bookings, presents_column=table_configs.presents_column
    )

    # (date, event) -> (tickets, num_tickets, total value, num orders)
    event_totals = generate_event_breakdown(parsed_bookings)

    if table_configs.presents_column is not None:
        train_times = list(table_configs.train_limits.keys())

        presents_by_age = summarise_presents_by_age(
            parsed_bookings, table_configs.presents_column
        )
        presents_by_train = summarise_presents_by_train(
            parsed_bookings, train_times=train_times, col_name=table_configs.presents_column
        )

        # date: train: count
        train_present_groups = presents_by_train.to_dict("index")

        # date: age: count
        age_present_groups = presents_by_age.to_dict("index")

        presents = {
            "by_train": train_present_groups,
            "by_day": presents_by_train.sum(axis="columns").to_dict(),
            "by_age": age_present_groups,
            "age_totals": presents_by_age.sum(axis="index").to_dict(),
        }
    else:
        presents = None
        train_times = []

    return render_template(
        "ticket_breakdown.html",
        totals=grand_totals,
        breakdown=event_totals,
        presents=presents,
        train_times=train_times,
        present_ages=PRESENT_AGES,
        active="breakdown",
        **global_vars(),
    )


@app.route("/tally")
def tally_index():
    """Render the index page for the present tally sheets."""
    data = session["csv_data"].copy()
    filtered_data = apply_filters(data, config)
    dates = get_dates(filtered_data)

    return render_template("tally_index.html", dates=dates, active="tally", **global_vars())


@app.route("/tally/<path:date>")
def tally_sheet(date):
    """Render the present tally sheet for the given date."""
    data = session["csv_data"].copy()
    filtered_data = apply_filters(data, config)
    table_configs: DataConfig = config["data_config"]

    if table_configs.presents_column is None:
        return render_tickets_error("No presents column specified")

    # Get the date from the URL
    try:
        day_str, month_str = date.split("/")
        day = int(day_str)
        month = int(month_str)
    except ValueError:
        return render_tickets_error("Invalid date")

    parsed_bookings = parse_bookings(
        filtered_data, table_configs.input_format, config["ticket prices"]
    )
    tally_data_df = generate_tally_data(
        parsed_bookings, table_configs.presents_column, day, month, table_configs.needs_column
    )
    tally_data, train_times = render_tally_data(tally_data_df, table_configs.train_limits)

    # Generate summary statistics
    tally_date = tally_data_df["date_time"].iloc[0]
    num_presents = tally_data_df["present_count"].sum()
    num_family = list(tally_data_df.groupby(["train_time"]).size().values)
    num_child = list(tally_data_df.groupby("train_time")["present_count"].sum().values)
    max_order_id = parsed_bookings["Order ID_formatted"].max()

    # Generate needs summaries
    with_needs = (
        tally_data_df[tally_data_df["needs_codes"] != ""]
        .groupby("train_time")["needs_codes"]
        .apply(list)
    )
    # add rows for all the trains
    with_needs = with_needs.reindex(index=train_times, fill_value=[])
    # get the max number of orders with needs on a train
    max_needs = with_needs.str.len().max()

    return render_template(
        "tally_sheet.html",
        train_times=train_times,
        tally_data=tally_data,
        date=tally_date.strftime("%a %d %b"),
        num_presents=num_presents,
        exported_at=datetime.now().strftime("%d-%b %H:%M"),
        max_order_id=max_order_id,
        num_family=num_family,
        num_child=num_child,
        with_needs=with_needs.to_dict(),
        max_needs=max_needs,
        active="tally",
        **global_vars(),
    )


# AJAX methods
@app.route("/prices", methods=["GET"])
def get_event_price():
    """Return the ticket prices for the given event substring."""
    event = request.args.get("event")

    if request.args.get("list") == "true":
        return sorted(config["ticket prices"].keys(), key=len, reverse=True)

    return config["ticket prices"].get(event, {})


@app.route("/prices", methods=["POST"])
def set_event_price():
    """Set the ticket prices for the given event substring."""
    event = request.form.get("event", "")
    print(request.form)

    if request.form.get("new") == "true":
        new_filter = request.form.get("new_filter")
        update_prices(new_filter, {})
    elif request.form.get("delete") == "true":
        # Delete price filter
        update_prices(event, None)
    else:
        prices = json.loads(request.form["prices"])

        new_filter = request.form.get("new_filter")
        if new_filter and new_filter != event:
            config["ticket prices"][new_filter] = config["ticket prices"].pop(event)
            event = new_filter

        # This will save the renamed event if it was changed
        update_prices(event, prices)

    return {"success": True}


def global_vars():
    """Provide global variables to the template."""
    return {
        "csv_name": session.get("csv_name"),
        "csv_uploaded": session.get("csv_uploaded"),
        "version": __version__,
        "config": {
            "csv_url": config["CSV URL"],
            "filter": config["product filter"],
            "hide_old": config["hide old orders"],
            "old_date": config["old order date"],
            "price_options": sorted(config["ticket prices"].keys(), key=len, reverse=True),
            "presents": config["data_config"].presents_column is not None,
        },
    }


def main():
    """Run the flask server."""
    app.run(debug=True)


if __name__ == "__main__":
    main()
