import re
from typing import Dict, List, Tuple, NamedTuple
from datetime import datetime, date as dt_date
from collections import defaultdict, Counter

from parse_ticket_sheet import extract_present_details, date_sort_item, calculate_walkin_price


class BookingSubTotal(NamedTuple):
    full_value_tickets: Dict[str, int]
    reduced_tickets: Dict[str, int]
    total_value: float
    total_saving: float
    total_extra_cost: float
    total_orders: int
    ticket_types: List[str]


# this is just a typehint
Bookings = List[List[str]]
BookingsBreakdown = Dict[str, Dict[str, BookingSubTotal]]


STANDARD_PRICES = {
    'Adult': 9.0,
    'Senior': 8.0,
    'Child': 7.0,
}

PREORDERED_TYPES = ['Adult', 'Senior', 'Child']


def parse_date(date_str: str) -> datetime:
    value_clean = re.sub(r'([0-9]+)(st|nd|rd|th)', r'\1', date_str).replace(',', '')
    return datetime.strptime(value_clean, '%A %B %d %Y %H:%M %p')


def group_by_date(bookings: Bookings, labels: List[str]) -> Dict[str, Bookings]:
    grouped_bookings = defaultdict(list)

    for booking in bookings:
        booking_dict = dict(zip(labels, booking))  # map columns to label names
        full_date = parse_date(booking_dict['Start date'])
        date = full_date.strftime('%d/%m/%y')

        grouped_bookings[date].append(booking)

    return grouped_bookings


def group_by_event(bookings: Bookings, labels: List[str]) -> Dict[str, Bookings]:
    grouped_bookings = defaultdict(list)

    for booking in bookings:
        booking_dict = dict(zip(labels, booking))  # map columns to label names
        event = booking_dict['Product title']

        grouped_bookings[event].append(booking)

    return grouped_bookings


def group_bookings(bookings: Bookings, labels: List[str]) -> Dict[str, Dict[str, Bookings]]:
    "Group bookings by date and then product name"
    grouped_bookings: Dict[str, Dict[str, Bookings]] = {}

    booking_date_groups = group_by_date(bookings, labels)
    for date, day_bookings in booking_date_groups.items():
        grouped_bookings[date] = group_by_event(day_bookings, labels)

    return grouped_bookings


def order_ticket_types(ticket_types: List[str]) -> List[str]:
    ticket_types_sorted = []

    ticket_types.sort()

    # A hack to manually place the default tickets in the right order
    for ticket_type in PREORDERED_TYPES:
        if ticket_type in ticket_types:
            ticket_types_sorted.append(ticket_type)

    for ticket_type in ticket_types:
        if ticket_type not in PREORDERED_TYPES:
            ticket_types_sorted.append(ticket_type)

    return ticket_types_sorted


def subtotal_orders(
    bookings: Bookings,
    labels: List[str],
    ticket_values: Dict[str, float],
) -> BookingSubTotal:
    full_value_tickets: Dict[str, int] = defaultdict(int)  # all keys map to 0 initially
    reduced_tickets: Dict[str, int] = defaultdict(int)
    ticket_types = []
    total_value = 0.0
    total_saving = 0.0
    total_orders = len(bookings)

    for booking in bookings:
        booking_dict = dict(zip(labels, booking))  # map columns to label names

        tickets = parse_tickets(booking_dict['Price categories'], booking=booking_dict)
        ticket_regular_rate = calculate_ticket_value(tickets, ticket_values)
        booking_price = float(calculate_walkin_price(booking_dict['Product price'], booking_dict))
        saving: float = max(0, ticket_regular_rate - booking_price)  # ignore negative savings

        total_value += booking_price
        total_saving += saving

        for ticket_name, ticket_qty, _ in tickets:
            if saving == 0.0:
                full_value_tickets[ticket_name] += ticket_qty
            else:
                reduced_tickets[ticket_name] += ticket_qty

            if ticket_name not in ticket_types:
                ticket_types.append(ticket_name)

    ticket_types_sorted = order_ticket_types(ticket_types)

    return BookingSubTotal(
        dict(full_value_tickets),
        dict(reduced_tickets),
        total_value,
        total_saving,
        0.0,
        total_orders,
        ticket_types_sorted,
    )


def parse_tickets(ticket_str: str, booking: Dict[str, str]) -> List[Tuple[str, int, float]]:
    ticket_output = []
    tickets = ticket_str.splitlines()  # convert "Price categories" field to a list of tickets

    if booking.get('Accompanying Adult'):
        try:
            adults, adult_value = booking['Accompanying Adult'].split('£')
        except ValueError:
            adults, adult_value = booking['Accompanying Adult'], '0.00'
        if adults != '0':
            tickets.append(f"Adult: {adults} (£{adult_value})")

    if booking.get('Accompanying Senior'):
        try:
            seniors, senior_value = booking['Accompanying Senior'].split('£')
        except ValueError:
            seniors, senior_value = booking['Accompanying Senior'], '0.00'
        if seniors != '0':
            tickets.append(f"Senior: {seniors} (£{senior_value})")

    for ticket in tickets:
        # each ticket line is in the format: <ticket name>: <quantity> (£<price>)
        # every thing before the first ':' in the ticket name
        ticket_name, ticket_field_str = ticket.split(':', maxsplit=1)
        ticket_fields = ticket_field_str.split()  # other fields are space-separated

        try:
            ticket_qty = int(ticket_fields[0])
        except IndexError:
            ticket_price = 0
        try:
            ticket_price = float(ticket_fields[1][2:-1])
        except IndexError:
            ticket_price = 0.0

        if ticket_name == 'Child':
            infant_qty = 0
            presents = (
                booking['Child Age (Nov)'].split('\n')
                + booking['Child Age (Dec)'].split('\n')
                + booking.get('Child Age (Non-internet)', '').splitlines()
            )
            for present in presents:
                if '0 to 1 yr' in present or '1 to 2 yr' in present:
                    infant_qty += 1
                    ticket_qty -= 1

            ticket_output.append(('Child', ticket_qty, 0.0))
            ticket_output.append(('Infant', infant_qty, 0.0))
        else:
            ticket_output.append((ticket_name, ticket_qty, ticket_price))

    return ticket_output


def calculate_ticket_value(
    tickets: List[Tuple[str, int, float]],
    ticket_values: Dict[str, float],
) -> float:
    total_cost = 0.0

    for ticket_name, ticket_qty, _ in tickets:
        ticket_price = ticket_values.get(ticket_name, 0)

        total_cost += ticket_qty * ticket_price

    return total_cost


def present_breakdown(bookings: Bookings, labels: List[str]) -> Dict[str, Dict[str, Dict[str, int]]]:
    presents = defaultdict(list)
    for booking in bookings:
        booking_dict = dict(zip(labels, booking))  # map columns to label names

        present_str = extract_present_details(booking_dict['Present Type'], booking_dict)
        present_list = [present.strip() for present in present_str.split(',')]
        train_date = date_sort_item(booking_dict['Start date'])
        for present in present_list:
            if present != '':
                presents[train_date].append(present)

    present_age_summary: Dict[str, Dict[str, int]] = defaultdict(Counter)
    present_train_summary: Dict[str, Dict[str, int]] = defaultdict(dict)

    for date_train, train_presents in presents.items():
        day = date_train.strftime('%d/%m/%y')
        train = date_train.strftime('%H:%M')

        present_age_summary[day].update(Counter(train_presents))
        present_train_summary[day][train] = len(train_presents)

    return {
        'by-age': {k: dict(v) for k, v in present_age_summary.items()},
        'by-train': dict(present_train_summary),
        'by-day': {day: sum(age.values()) for day, age in present_train_summary.items()}
    }


def present_totals(present_age_breakdown: Dict[dt_date, Dict[str, int]]) -> Dict[str, int]:
    totals: Dict[str, int] = defaultdict(int)
    for day_totals in present_age_breakdown.values():
        for present, qty in day_totals.items():
            totals[present] += qty

    return dict(totals)
