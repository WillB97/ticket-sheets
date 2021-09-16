#!/usr/bin/env python3
import re
import csv
import argparse
from typing import Dict, List, Tuple, NamedTuple
from pathlib import Path
from datetime import datetime
from collections import defaultdict


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
    'Adult': 9,
    'Senior': 8,
    'Child': 7,
}


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
    value_clean = re.sub(r'([0-9]+)(st|nd|rd|th)', r'\1', date_str)
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
    total_extra_cost = 0.0  # the value above a regular service, required for tax calculations
    total_orders = len(bookings)

    for booking in bookings:
        booking_dict = dict(zip(labels, booking))  # map columns to label names

        tickets = parse_tickets(booking_dict['Price categories'])
        ticket_regular_rate = calculate_ticket_value(tickets, ticket_values)
        booking_price = float(booking_dict['Product price'].replace('&pound;', ''))
        saving: float = max(0, ticket_regular_rate - booking_price)  # ignore negative savings

        total_value += booking_price
        total_saving += saving
        total_extra_cost += ticket_extra_cost(tickets)

        for ticket_name, ticket_qty, _ in tickets:
            if saving == 0.0:
                full_value_tickets[ticket_name] += ticket_qty
            else:
                reduced_tickets[ticket_name] += ticket_qty

            if ticket_name not in ticket_types:
                ticket_types.append(ticket_name)

    ticket_types.sort()

    return BookingSubTotal(
        dict(full_value_tickets),
        dict(reduced_tickets),
        total_value,
        total_saving,
        total_extra_cost,
        total_orders,
        ticket_types,
    )


def parse_tickets(ticket_str: str) -> List[Tuple[str, int, float]]:
    ticket_output = []
    tickets = ticket_str.splitlines()  # convert "Price categories" field to a list of tickets

    for ticket in tickets:
        # each ticket line is in the format: <ticket name>: <quantity> (£<price>)
        # every thing before the first ':' in the ticket name
        ticket_name, ticket_field_str = ticket.split(':', maxsplit=1)
        ticket_fields = ticket_field_str.split()  # other fields are space-separated

        ticket_qty = int(ticket_fields[0])
        ticket_price = float(ticket_fields[1][2:-1])

        if ticket_name == 'Child' and ticket_qty > 1:
            ticket_output.append(('Family Child', ticket_qty, ticket_price))
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


def ticket_extra_cost(tickets: List[Tuple[str, int, float]]) -> float:
    "Calculate the value above a regular service, required for tax calculations"
    extra_cost = 0.0

    for ticket_name, ticket_qty, ticket_value in tickets:
        # ticket_price = STANDARD_PRICES.get(ticket_name, 0)
        # ticket_qty * ticket_price

        # TODO figure this out
        pass

    return extra_cost


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
