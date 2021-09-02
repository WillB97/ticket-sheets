#!/usr/bin/env python3
import csv
import json
import requests
from io import TextIOWrapper
from flask import Flask, Markup, url_for, request, redirect, render_template
from datetime import datetime

import parse_ticket_sheet

app = Flask(__name__)

CONFIG_FILE = 'config.json'

FILTER_STRING = ''
CSV_URL = ''
HIDE_OLD_ORDERS = False
OLD_ORDER_DATE = ''


def insert_html_newlines(value: str) -> str:
    return Markup(value.replace('\n', '<br>'))


table_configuration = [
    # (<input column heading>, <output column label>, <optional conversion function>),
    ('Order ID', 'Order', None),
    ('Booking ID', 'Booking', None),
    ('Customer first name', 'First name', None),
    ('Customer last name', 'Last name', None),
    ('Quantity', 'Qty.', None),
    (None, 'Issued', None),
    (None, 'Infants', None),
    (None, 'QR?', None),
    ('Product price', 'Paid', parse_ticket_sheet.tidy_price),
    ('Price categories', 'Price categories', insert_html_newlines),
]

column_align = {
    'Order': 'center',
    'Booking': 'center',
    'First name': 'right',
    'Last name': 'left',
    'Qty.': 'center',
    'Issued': 'center',
    'Infants': 'center',
    'QR?': 'center',
    'Paid': 'center',
    'Price categories': 'left',
}


def parse_bookings(raw_data):
    parsed_bookings = []
    earliest_order_date = datetime.strptime(OLD_ORDER_DATE, '%Y-%m-%d')
    labels = raw_data[0]  # top row is labels

    bookings = parse_ticket_sheet.sort_bookings(raw_data[1:], labels)

    for row in bookings:
        booking = dict(zip(labels, row))  # map columns to label names

        if HIDE_OLD_ORDERS:  # filter bookings by date
            if parse_ticket_sheet.date_sort_item(booking['Start date']) < earliest_order_date:
                continue

        if parse_ticket_sheet.filter_booking(booking):
            parsed_bookings.append([parse_ticket_sheet.format_booking_row(booking), booking])

    return parsed_bookings


def prepare_booking_table_values(processed_bookings, header):
    rendered_bookings = []
    last_seen_date = datetime(1970, 1, 1, 0, 0)  # use minimum date so the first date in printed

    for booking, original_booking in processed_bookings:
        if parse_ticket_sheet.GROUP_BOOKINGS_BY_DATE:
            booking_date = parse_ticket_sheet.date_sort_item(original_booking['Start date'])
            if booking_date != last_seen_date:
                rendered_bookings.append({
                    'booking_type': 'date',
                    'date': parse_ticket_sheet.format_group_date(booking_date),
                })
                last_seen_date = booking_date

        rendered_bookings.append({
            'booking_type': 'order',
            'booking': dict(zip(header, booking)),
        })

    return rendered_bookings


def render_order_table(orders):
    if not orders:
        return render_template(
            'index.html',
            config={
                'csv_url': CSV_URL,
                'filter': FILTER_STRING,
                'hideOld': HIDE_OLD_ORDERS,
                'old_date': OLD_ORDER_DATE,
            },
            error="No Ticket Data Found"
        )

    header = [column[1] for column in parse_ticket_sheet.table_configuration]

    parsed_bookings = parse_bookings(orders)
    rendered_bookings = prepare_booking_table_values(parsed_bookings, header)

    return render_template(
        'index.html',
        header=header,
        bookings=rendered_bookings,
        align=column_align,
        columns=len(header),
        config={
            'csv_url': CSV_URL,
            'filter': FILTER_STRING,
            'hideOld': HIDE_OLD_ORDERS,
            'old_date': OLD_ORDER_DATE,
        }
    )


@app.route('/')
def ticket_sheet():
    # Setup column layout & filter
    parse_ticket_sheet.table_configuration = table_configuration
    parse_ticket_sheet.BOOKING_FILTER_STRING = FILTER_STRING

    # with open(TICKET_DUMP_FILE, 'r', errors='ignore') as f:
    #     data_list = list(csv.reader(f, delimiter=','))

    r = requests.get(CSV_URL)

    if r.status_code != 200:
        return render_template(
            'index.html',
            config={
                'csv_url': CSV_URL,
                'filter': FILTER_STRING,
                'hideOld': HIDE_OLD_ORDERS,
                'old_date': OLD_ORDER_DATE,
            },
            error="Failed to fetch CSV data"
        )

    data_list = list(csv.reader(r.text.splitlines(keepends=True), delimiter=','))

    return render_order_table(data_list)


@app.route('/manual', methods=['GET'])
def prepare_upload():
    return render_template(
        'index.html',
        config={
            'csv_url': CSV_URL,
            'filter': FILTER_STRING,
            'hideOld': HIDE_OLD_ORDERS,
            'old_date': OLD_ORDER_DATE,
        },
        error="Please upload a CSV"
    )


@app.route('/manual', methods=['POST'])
def uploaded_tickets():
    # Setup column layout & filter
    parse_ticket_sheet.table_configuration = table_configuration
    parse_ticket_sheet.BOOKING_FILTER_STRING = FILTER_STRING

    f = request.files['fileupload']

    csv_str = TextIOWrapper(f).read()

    data_list = list(csv.reader(csv_str.splitlines(keepends=True), delimiter=','))

    return render_order_table(data_list)


@app.route('/config', methods=['POST'])
def update_config():
    global FILTER_STRING, CSV_URL, HIDE_OLD_ORDERS, OLD_ORDER_DATE

    # store request data
    CSV_URL = request.form.get('csvUrl', '')
    FILTER_STRING = request.form.get('filter', '')
    HIDE_OLD_ORDERS = (request.form.get('hideOld', '') == 'hide')
    OLD_ORDER_DATE = request.form.get('filterDate', '')

    save_config()
    return redirect(url_for('ticket_sheet'))


def save_config():
    config = {
        "product filter": FILTER_STRING,
        "CSV URL": CSV_URL,
        "hide old orders": HIDE_OLD_ORDERS,
        "old order date": OLD_ORDER_DATE,
    }

    print(f"New config: {config}")

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def load_config():
    global FILTER_STRING, CSV_URL, HIDE_OLD_ORDERS, OLD_ORDER_DATE

    with open(CONFIG_FILE, 'r') as f:
        config_data = json.load(f)

    FILTER_STRING = config_data['product filter']
    CSV_URL = config_data['CSV URL']
    HIDE_OLD_ORDERS = config_data['hide old orders']
    OLD_ORDER_DATE = config_data['old order date']


load_config()

if __name__ == "__main__":
    app.run(debug=True)
