#!/usr/bin/env python3
import csv
import json
import requests
from io import TextIOWrapper
from flask import Flask, Markup, url_for, request, redirect, render_template
from datetime import datetime
from collections import defaultdict

import parse_ticket_sheet
import event_breakdown

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


def prepare_booking_table_values(processed_bookings, header, day_totals=None):
    rendered_bookings = []
    last_seen_date = datetime(1970, 1, 1, 0, 0)  # use minimum date so the first date in printed

    for booking, original_booking in processed_bookings:
        if parse_ticket_sheet.GROUP_BOOKINGS_BY_DATE:
            booking_date = parse_ticket_sheet.date_sort_item(original_booking['Start date'])
            if booking_date != last_seen_date:
                if (
                    last_seen_date != datetime(1970, 1, 1, 0, 0)
                    and day_totals is not None
                ):
                    try:
                        totals = day_totals[last_seen_date.strftime('%d/%m/%y')]
                        rendered_bookings.append({'booking_type': 'totals', 'data': totals})
                    except KeyError:
                        # skip totals when they are missing
                        pass

                rendered_bookings.append({
                    'booking_type': 'date',
                    'date': parse_ticket_sheet.format_group_date(booking_date),
                })
                last_seen_date = booking_date

        rendered_bookings.append({
            'booking_type': 'order',
            'booking': dict(zip(header, booking)),
        })

    if day_totals is not None:
        try:
            totals = day_totals[last_seen_date.strftime('%d/%m/%y')]
            rendered_bookings.append({'booking_type': 'totals', 'data': totals})
        except KeyError:
            # skip totals when they are missing
            pass

    return rendered_bookings


def prepare_ticket_breakdown(processed_bookings, labels):
    totals: event_breakdown.BookingsBreakdown = defaultdict(dict)

    grouped_bookings = event_breakdown.group_bookings(processed_bookings, labels)

    for date, day_bookings in grouped_bookings.items():
        for event, booking_group in day_bookings.items():
            # TODO: setup support for per-event pricing
            ticket_values = {}
            totals[date][event] = event_breakdown.subtotal_orders(booking_group, labels, ticket_values)

    return dict(totals)


def generate_day_totals(breakdown):
    daily_totals = {}

    for date, date_group in breakdown.items():
        num_tickets = 0
        num_orders = 0
        total_cost = 0.0
        ticket_totals = defaultdict(int)

        for _, event_totals in date_group.items():
            num_tickets += sum(event_totals.full_value_tickets.values())
            num_tickets += sum(event_totals.reduced_tickets.values())
            num_orders += event_totals.total_orders
            total_cost += event_totals.total_value

            for ticket, qty in event_totals.full_value_tickets.items():
                ticket_totals[ticket] += qty

            for ticket, qty in event_totals.reduced_tickets.items():
                ticket_totals[ticket] += qty

        daily_totals[date] = {
            'num_tickets': num_tickets,
            'num_orders': num_orders,
            'total_cost': total_cost,
            'ticket_totals': ticket_totals,
        }

    return daily_totals


def render_order_table(orders, csv_name=None, csv_data='', fetch_date=None):
    if not orders:
        return render_tickets_error("No Ticket Data Found")

    header = [column[1] for column in parse_ticket_sheet.table_configuration]

    parsed_bookings = parse_bookings(orders)
    filtered_bookings = [booking[1].values() for booking in parsed_bookings]
    labels = parsed_bookings[0][1].keys()

    breakdown = prepare_ticket_breakdown(filtered_bookings, labels)
    daily_totals = generate_day_totals(breakdown)
    rendered_bookings = prepare_booking_table_values(parsed_bookings, header, daily_totals)

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
        },
        csv_name=csv_name,
        csv_data=csv_data,
        fetch_date=fetch_date,
        breakdown=breakdown,
    )


def render_tickets_error(error, err_str=None):
    return render_template(
        'index.html',
        config={
            'csv_url': CSV_URL,
            'filter': FILTER_STRING,
            'hideOld': HIDE_OLD_ORDERS,
            'old_date': OLD_ORDER_DATE,
        },
        error=error,
        error_string=err_str
    )


@app.route('/auto')
def ticket_sheet():
    # Setup column layout & filter
    parse_ticket_sheet.table_configuration = table_configuration
    parse_ticket_sheet.BOOKING_FILTER_STRING = FILTER_STRING

    try:
        r = requests.get(CSV_URL, timeout=10)
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
        return render_tickets_error("Failed to fetch CSV data", err_str=e)

    except requests.exceptions.RequestException as e:
        return render_tickets_error("An error occured while fetching CSV data", err_str=e)

    if r.status_code != 200:
        return render_tickets_error("Failed to fetch CSV data", err_str=f"Error code: {r.status_code}")

    if r.headers['Content-Type'].find('text/csv') == -1:
        return render_tickets_error("Retrieved data was not a CSV", err_str="Check the CSV URL.")

    data_list = list(csv.reader(r.text.splitlines(keepends=True), delimiter=','))

    return render_order_table(data_list, fetch_date=datetime.now().strftime('%c'))


@app.route('/')
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

    return render_order_table(data_list, f.filename, csv_data=json.dumps(data_list))


@app.route('/config', methods=['GET'])
def config_get_redirect():
    return redirect(url_for('prepare_upload'))


@app.route('/config', methods=['POST'])
def update_config():
    global FILTER_STRING, CSV_URL, HIDE_OLD_ORDERS, OLD_ORDER_DATE

    # store request data
    CSV_URL = request.form.get('csvUrl', '')
    FILTER_STRING = request.form.get('filter', '')
    HIDE_OLD_ORDERS = (request.form.get('hideOld', '') == 'hide')
    OLD_ORDER_DATE = request.form.get('filterDate', '')

    save_config()

    try:
        # try to render the cached CSV data if it is available
        csv_data = json.loads(request.form.get('csvData'))
        return render_order_table(csv_data, request.form.get('csvName'), csv_data=csv_data)
    except (ValueError, json.JSONDecodeError):
        # if there is no CSV data just return to the previous page
        return redirect(request.referrer)


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
