#!/usr/bin/env python3
import re
import csv
import argparse
from typing import Dict, List, Tuple, NamedTuple
from pathlib import Path
from datetime import datetime, date as dt_date
from collections import defaultdict, Counter

from parse_ticket_sheet import extract_present_details, date_sort_item


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

PREORDERED_TYPES = ['Adult', 'Senior', 'Child', 'Family Child']


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'filename',
        help="The CSV file to parse",
        type=Path
    )
    parser.add_argument(
        '-A', '--adult',
        help="Set the value of adult tickets",
        default=9.0,
        type=float
    )
    parser.add_argument(
        '-S', '--senior',
        help="Set the value of senior tickets",
        default=8.0,
        type=float
    )
    parser.add_argument(
        '-C', '--child',
        help="Set the value of child tickets",
        default=7.0,
        type=float
    )
    parser.add_argument(
        '-F', '--family',
        help="Set the value of family child tickets",
        default=6.0,
        type=float
    )
    return parser.parse_args()


def read_bookings(filename: str) -> Bookings:
    with open(filename, 'r', errors='ignore') as f:  # ignore unicode errors
        data_list = list(csv.reader(f, delimiter=','))  # convert csv data to 2D list

        if data_list == []:
            print("No CSV rows found")
            exit(1)

    return data_list


def calculate_totals(
    bookings: Bookings,
    labels: List[str],
    ticket_values: Dict[str, float],
) -> Dict[str, Dict[str, BookingSubTotal]]:
    totals: BookingsBreakdown = defaultdict(dict)

    grouped_bookings = group_bookings(bookings, labels)

    for date, day_bookings in grouped_bookings.items():
        for event, booking_group in day_bookings.items():
            totals[date][event] = subtotal_orders(booking_group, labels, ticket_values)

    return totals


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
    standard_prices: Dict[str, float] = STANDARD_PRICES,
) -> BookingSubTotal:
    full_value_tickets: Dict[str, int] = defaultdict(int)  # all keys map to 0 initially
    reduced_tickets: Dict[str, int] = defaultdict(int)
    ticket_types = []
    total_value = 0.0
    total_saving = 0.0
    total_extra_cost = 0.0  # the value above a regular service, required for tax calculations
    total_orders = len(bookings)

    for booking in bookings:
        booking_dict = dict(zip(labels, booking))  # map columns to label names

        tickets = parse_tickets(booking_dict['Price categories'], booking=booking_dict)
        ticket_regular_rate = calculate_ticket_value(tickets, ticket_values)
        booking_price = float(booking_dict['Product price'].replace('&pound;', '').replace('£', ''))
        saving: float = max(0, ticket_regular_rate - booking_price)  # ignore negative savings

        total_value += booking_price
        total_saving += saving
        total_extra_cost += ticket_extra_cost(tickets, standard_prices)

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
        total_extra_cost,
        total_orders,
        ticket_types_sorted,
    )


def parse_tickets(ticket_str: str, booking: Dict[str, str]) -> List[Tuple[str, int, float]]:
    ticket_output = []
    tickets = ticket_str.splitlines()  # convert "Price categories" field to a list of tickets

    if booking.get('Accompanying Adult'):
        adults, adult_value = booking['Accompanying Adult'].split('£')
        if adults != '0':
            tickets.append(f"Adult: {adults} (£{adult_value})")

    if booking.get('Accompanying Senior'):
        seniors, senior_value = booking['Accompanying Senior'].split('£')
        if seniors != '0':
            tickets.append(f"Senior: {seniors} (£{senior_value})")

    for ticket in tickets:
        # each ticket line is in the format: <ticket name>: <quantity> (£<price>)
        # every thing before the first ':' in the ticket name
        ticket_name, ticket_field_str = ticket.split(':', maxsplit=1)
        ticket_fields = ticket_field_str.split()  # other fields are space-separated

        ticket_qty = int(ticket_fields[0])
        ticket_price = float(ticket_fields[1][2:-1])

        if ticket_name == 'Child':
            infant_qty = 0
            presents = booking['Child Age (Nov)'].split('\n') + booking['Child Age (Dec)'].split('\n')
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


def ticket_extra_cost(tickets: List[Tuple[str, int, float]], standard_prices: Dict[str, float]) -> float:
    "Calculate the value above a regular service, required for tax calculations"
    extra_cost = 0.0

    for ticket_name, ticket_qty, ticket_value in tickets:
        # ticket_price = standard_prices.get(ticket_name, 0)
        # ticket_qty * ticket_price

        # TODO figure this out
        pass

    return extra_cost


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
        'by-train': dict(present_train_summary)
    }


def present_totals(present_age_breakdown: Dict[dt_date, Dict[str, int]]) -> Dict[str, int]:
    totals: Dict[str, int] = defaultdict(int)
    for day_totals in present_age_breakdown.values():
        for present, qty in day_totals.items():
            totals[present] += qty

    return dict(totals)


def print_totals(totals: BookingsBreakdown) -> None:
    for date, day_totals in totals.items():
        print(f"Totals for {date}")
        for event, event_totals in day_totals.items():
            print(f"Totals for {event}")

            print("  Full-price tickets")
            for ticket_name, ticket_qty in event_totals.full_value_tickets.items():
                print(f"  {ticket_name:<6}: {ticket_qty:>4}")
            print()

            print("  Reduced tickets")
            for ticket_name, ticket_qty in event_totals.reduced_tickets.items():
                print(f"  {ticket_name:<6}: {ticket_qty:>4}")
            print()

            print(f"  Orders: {event_totals.total_orders:>4}")
            print(f"  Income:        £{event_totals.total_value:.2f}")
            print(f"  Extra value:   £{event_totals.total_extra_cost:.2f}")
            print(f"  Total savings: £{event_totals.total_saving:.2f}")
            print()

        print('-' * 30)
        print()


def main() -> None:
    args = parse_args()

    ticket_values = {
        'Adult': args.adult, 'Senior': args.senior,
        'Child': args.child, 'Family Child': args.family
    }

    bookings = read_bookings(args.filename)

    totals = calculate_totals(bookings[1:], labels=bookings[0], ticket_values=ticket_values)

    print_totals(totals)


if __name__ == '__main__':
    main()
