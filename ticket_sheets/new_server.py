#!/usr/bin/env python3
"""Ticket-sheets flask server."""

from datetime import datetime

import pandas as pd
from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.exceptions import InternalServerError

from flask_session import Session

from .config import DataConfig, get_config, refresh_config, update_config
from .parse_data import apply_filters, format_for_table, get_dates, parse_bookings, parse_csv

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
    data = session["csv_data"]
    filtered_data = apply_filters(data, config)
    table_configs: DataConfig = config["data_config"]

    parsed_bookings = parse_bookings(filtered_data, table_configs.input_format)
    # Also include daily totals
    rendered_bookings = format_for_table(
        parsed_bookings, table_configs.ticket_config, daily_totals=True
    )

    header = [column.title for column in table_configs.ticket_config.columns]
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
    data = session["csv_data"]
    filtered_data = apply_filters(data, config)
    table_configs: DataConfig = config["data_config"]

    parsed_bookings = parse_bookings(filtered_data, table_configs.input_format)
    rendered_bookings = format_for_table(parsed_bookings, table_configs.alpha_config)

    header = [column.title for column in table_configs.alpha_config.columns]
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


@app.route("/tally")
def tally_index():
    """Render the index page for the present tally sheets."""
    data = session["csv_data"]
    filtered_data = apply_filters(data, config)
    dates = get_dates(filtered_data)

    return render_template("tally_index.html", dates=dates, active="tally", **global_vars())


def global_vars():
    """Provide global variables to the template."""
    return {
        "csv_name": session.get("csv_name"),
        "csv_uploaded": session.get("csv_uploaded"),
        "config": {
            "csv_name": session.get("csv_name"),
            "csv_uploaded": session.get("csv_uploaded"),
            "csv_url": config["CSV URL"],
            "filter": config["product filter"],
            "hide_old": config["hide old orders"],
            "old_date": config["old order date"],
        },
    }


def main():
    """Run the flask server."""
    app.run(debug=True)


if __name__ == "__main__":
    main()
