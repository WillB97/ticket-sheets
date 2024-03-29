#!/usr/bin/env python3
import csv
import json
import requests
from os import urandom
from io import TextIOWrapper
from flask import Flask, Markup, url_for, request, redirect, render_template, session
from flask_session import Session
from typing import Dict
from datetime import datetime
from collections import defaultdict

import parse_ticket_sheet
import event_breakdown

app = Flask(__name__)

app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_USE_SIGNER"] = True
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

CONFIG_FILE = 'config.json'

FILTER_STRING = ''
CSV_URL = ''
HIDE_OLD_ORDERS = False
OLD_ORDER_DATE = ''
TICKET_PRICES: Dict[str, Dict[str, Dict[str, float]]] = {}


def insert_html_newlines(value: str, booking: Dict[str, str]) -> str:
    return Markup(value.replace('\n', '<br>'))


table_configuration = [
    # (<input column heading>, <output column label>, <optional conversion function>),
    ('Order ID', 'Order', None),
    ('Booking ID', 'Booking', None),
    ('Start date', 'Train', parse_ticket_sheet.parse_train_time),
    ('Customer first name', 'First name', None),
    ('Customer last name', 'Last name', None),
    ('Quantity', 'Qty.', None),
    (None, 'Issued', None),
    (None, 'Infants', None),
    ('Product price', 'Paid', parse_ticket_sheet.tidy_price),
    ('Price categories', 'Price categories', insert_html_newlines),
    ('Special Needs', 'Notes', None),
]

alpha_table_configuration = [
    # (<input column heading>, <output column label>, <optional conversion function>),
    ('Order ID', 'Order', None),
    ('Booking ID', 'Booking', None),
    ('Start date', 'Date', parse_ticket_sheet.parse_train_date),
    ('Start date', 'Train', parse_ticket_sheet.parse_train_time),
    ('Customer first name', 'First name', None),
    ('Customer last name', 'Last name', None),
    ('Quantity', 'Qty.', None),
    ('Product price', 'Paid', parse_ticket_sheet.tidy_price),
    ('Price categories', 'Price categories', insert_html_newlines),
    ('Special Needs', 'Notes', None),
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
    'Train': 'center',
    'Date': 'center',
    'Notes': 'center',
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
            if booking_date.date() != last_seen_date.date():
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
            event_prices = TICKET_PRICES.get(f"{date} {event}", {})

            ticket_values = event_prices.get('event', event_breakdown.STANDARD_PRICES)
            standard_prices = event_prices.get('standard', event_breakdown.STANDARD_PRICES)

            totals[date][event] = event_breakdown.subtotal_orders(
                booking_group,
                labels,
                ticket_values,
                standard_prices,
            )

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

        ticket_types = event_breakdown.order_ticket_types(list(ticket_totals.keys()))

        ticket_totals_sorted = {}

        for ticket_type in ticket_types:  # reinsert all keys in the correct order
            ticket_totals_sorted[ticket_type] = ticket_totals[ticket_type]

        daily_totals[date] = {
            'num_tickets': num_tickets,
            'num_orders': num_orders,
            'total_cost': total_cost,
            'ticket_totals': ticket_totals_sorted,
        }

    return daily_totals


def grand_total_orders(breakdown):
    totals = {'total_value': 0, 'total_orders': 0, 'total_tickets': 0}
    total_types = defaultdict(int)

    for date, day_bookings in breakdown.items():
        for event, event_bookings in day_bookings.items():
            totals['total_value'] += event_bookings.total_value
            totals['total_orders'] += event_bookings.total_orders
            totals['total_tickets'] += sum(event_bookings.full_value_tickets.values())
            totals['total_tickets'] += sum(event_bookings.reduced_tickets.values())
            for ticket, qty in event_bookings.full_value_tickets.items():
                total_types[ticket] += qty
            for ticket, qty in event_bookings.reduced_tickets.items():
                total_types[ticket] += qty

    total_types['Child'] += total_types['Family Child']
    del total_types['Family Child']
    totals['total_types'] = dict(total_types)
    return totals


def render_tickets_error(error, err_str=None):
    return render_template(
        'error.html',
        error=error,
        error_string=err_str
    )


@app.before_request
def load_fresh_config():
    """
    Under gunicorn different instances will respond to requests
    so the loaded config may have been updated
    """
    load_config()


@app.route('/auto')
def ticket_sheet():
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

    session['csv_name'] = f"Auto ({datetime.now().strftime('%c')})"
    session['csv_data'] = data_list
    return redirect(url_for('ticket_table'))


@app.route('/')
@app.route('/upload', methods=['GET'])
def prepare_upload():
    return render_template(
        'upload.html',
        config={'csv_url': CSV_URL},
        active='upload'
    )


@app.route('/upload', methods=['POST'])
def uploaded_tickets():
    try:
        f = request.files['fileupload']

        csv_str = TextIOWrapper(f, encoding='utf-8').read()

        data_list = list(csv.reader(csv_str.splitlines(keepends=True), delimiter=','))

        if not data_list:
            return render_template(
                'upload.html',
                config={'csv_url': CSV_URL},
                error="No Ticket Data Found",
                active='upload'
            )

        session['csv_name'] = f.filename
        session['csv_data'] = data_list
        session['csv_uploaded'] = datetime.now().strftime('%d-%b %H:%M')
        return redirect(url_for('ticket_table'))
    except KeyError:
        return render_template(
            'upload.html',
            config={'csv_url': CSV_URL},
            error="Please upload a valid CSV",
            active='upload'
        )


@app.route('/config-url', methods=['POST'])
def update_config_url():
    global CSV_URL

    # store request data
    CSV_URL = request.form.get('csvUrl', '')
    save_config()

    # return to the previous page
    return redirect(request.referrer)


@app.route('/config', methods=['POST'])
def update_config():
    global FILTER_STRING, HIDE_OLD_ORDERS, OLD_ORDER_DATE

    # store request data
    FILTER_STRING = request.form.get('filter', '')
    HIDE_OLD_ORDERS = (request.form.get('hideOld', '') == 'hide')
    OLD_ORDER_DATE = request.form.get('filterDate', '')

    save_config()

    # return to the previous page
    return redirect(request.referrer)


@app.route('/tickets')
def ticket_table():
    try:
        orders = session['csv_data']
    except KeyError:
        return render_tickets_error("Please upload a CSV")

    if not orders:
        return render_tickets_error("No Ticket Data Found")

    # Setup column layout & filter
    parse_ticket_sheet.table_configuration = table_configuration
    parse_ticket_sheet.BOOKING_FILTER_STRING = FILTER_STRING

    header = [column[1] for column in parse_ticket_sheet.table_configuration]

    parsed_bookings = parse_bookings(orders)
    filtered_bookings = [booking[1].values() for booking in parsed_bookings]

    try:
        labels = parsed_bookings[0][1].keys()
    except IndexError:
        # no bookings in parsed_bookings
        breakdown = {}
    else:
        breakdown = prepare_ticket_breakdown(filtered_bookings, labels)

    daily_totals = generate_day_totals(breakdown)
    rendered_bookings = prepare_booking_table_values(parsed_bookings, header, daily_totals)

    return render_template(
        'ticket_table.html',
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
        csv_name=session.get('csv_name'),
        csv_uploaded=session.get('csv_uploaded'),
        active='tickets'
    )


@app.route('/alpha')
def alphabetical_orders():
    try:
        orders = session['csv_data']
    except KeyError:
        return render_tickets_error("Please upload a CSV")

    if not orders:
        return render_tickets_error("No Ticket Data Found")

    old_group_bookings = parse_ticket_sheet.GROUP_BOOKINGS_BY_DATE
    old_sort_order = parse_ticket_sheet.column_sorts

    try:
        # Setup column layout & filter
        parse_ticket_sheet.table_configuration = alpha_table_configuration
        parse_ticket_sheet.BOOKING_FILTER_STRING = FILTER_STRING

        parse_ticket_sheet.GROUP_BOOKINGS_BY_DATE = False
        parse_ticket_sheet.column_sorts = {'Customer first name': 'ASC', 'Customer last name': 'ASC'}

        header = [column[1] for column in parse_ticket_sheet.table_configuration]

        parsed_bookings = parse_bookings(orders)
        rendered_bookings = prepare_booking_table_values(parsed_bookings, header)
    finally:
        parse_ticket_sheet.GROUP_BOOKINGS_BY_DATE = old_group_bookings
        parse_ticket_sheet.column_sorts = old_sort_order

    return render_template(
        'ticket_table.html',
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
        csv_name=session.get('csv_name'),
        no_totals=True,
        show_filter=True,
        active='alpha'
    )


@app.route('/breakdown')
def ticket_breakdown():
    try:
        orders = session['csv_data']
    except KeyError:
        return render_tickets_error("Please upload a CSV")

    if not orders:
        return render_tickets_error("No Ticket Data Found")

    # Setup column layout & filter
    parse_ticket_sheet.table_configuration = table_configuration
    parse_ticket_sheet.BOOKING_FILTER_STRING = FILTER_STRING

    parsed_bookings = parse_bookings(orders)
    filtered_bookings = [booking[1].values() for booking in parsed_bookings]

    try:
        labels = parsed_bookings[0][1].keys()
    except IndexError:
        # no bookings in parsed_bookings
        breakdown = {}
    else:
        breakdown = prepare_ticket_breakdown(filtered_bookings, labels)

    return render_template(
        'ticket_breakdown.html',
        config={
            'filter': FILTER_STRING,
            'hideOld': HIDE_OLD_ORDERS,
            'old_date': OLD_ORDER_DATE,
        },
        csv_name=session.get('csv_name'),
        csv_uploaded=session.get('csv_uploaded'),
        breakdown=breakdown,
        totals=grand_total_orders(breakdown),
        active='breakdown'
    )


# AJAX methods
@app.route('/prices', methods=['GET'])
def get_event_price():
    event = request.args.get('event')
    event_prices = TICKET_PRICES.get(event, {})

    return {
        'event': event_prices.get('event', event_breakdown.STANDARD_PRICES),
        'standard': event_prices.get('standard', event_breakdown.STANDARD_PRICES),
    }


@app.route('/prices', methods=['POST'])
def set_event_price():
    event = request.form['event']
    prices = json.loads(request.form['prices'])

    TICKET_PRICES[event] = prices

    save_config()

    return {'success': True}


def save_config():
    config = {
        "product filter": FILTER_STRING,
        "CSV URL": CSV_URL,
        "hide old orders": HIDE_OLD_ORDERS,
        "old order date": OLD_ORDER_DATE,
    }

    print(f"New config: {config}")

    config['secret_key'] = app.secret_key
    config['ticket prices'] = TICKET_PRICES

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=4)


def load_config():
    global FILTER_STRING, CSV_URL, HIDE_OLD_ORDERS, OLD_ORDER_DATE, TICKET_PRICES

    with open(CONFIG_FILE, 'r') as f:
        config_data = json.load(f)

    FILTER_STRING = config_data['product filter']
    CSV_URL = config_data['CSV URL']
    HIDE_OLD_ORDERS = config_data['hide old orders']
    OLD_ORDER_DATE = config_data['old order date']
    TICKET_PRICES = config_data.get('ticket prices', {})

    if app.secret_key is None:
        if config_data.get('secret_key') is None:
            app.secret_key = urandom(24).hex()
        else:
            app.secret_key = config_data['secret_key']

        save_config()


load_config()

if __name__ == "__main__":
    app.run(debug=True)
