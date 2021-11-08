#!/usr/bin/env python3
import re
import csv
import sys
from typing import Dict, List
from pathlib import Path
from datetime import datetime


## Field conversion functions ##
def simplify_product(value: str, booking: Dict[str, str]) -> str:
    value = value.replace('Weekend', 'w/e')
    value = value.replace('- Day Ticket', '')
    value = value.replace('Ticket', '')
    return value.strip()


def simplify_date(value: str, booking: Dict[str, str]) -> str:
    value_clean = re.sub(r'([0-9]+)(st|nd|rd|th)', r'\1', value).replace(',', '')
    date_value = datetime.strptime(value_clean, '%A %B %d %Y %I:%M %p')
    return date_value.strftime('%a %d/%m')


def tidy_price(value: str, booking: Dict[str, str]) -> str:
    return value.replace('&pound;', '').replace('£', '')


# TODO different format w/ prices
def parse_ticket_types(value: str, booking: Dict[str, str]) -> str:
    ticket_strings = []
    tickets = value.splitlines()  # convert "Price categories" field to a list of tickets

    for ticket in tickets:
        # each ticket line starts in the format: <ticket name>: <quantity> (£<price>)
        ticket_fields = ticket.split()
        ticket_name = ticket_fields[0][:-1]
        ticket_qty = int(ticket_fields[1])
        # ticket_price = float(ticket_fields[2][2:-1])

        ticket_strings.append(f"{ticket_name[0]}:{ticket_qty}")

    return ', '.join(ticket_strings)


def parse_train_time(value: str, booking: Dict[str, str]) -> str:
    full_date_str = date_sort_item(value)
    return full_date_str.strftime('%H:%M')


def parse_train_date(value: str, booking: Dict[str, str]) -> str:
    full_date_str = date_sort_item(value)
    return full_date_str.strftime('%d/%m')


def include_custom_tickets(value: str, booking: Dict[str, str]) -> str:
    if booking.get('Accompanying Adult'):
        try:
            adults, adult_value = booking['Accompanying Adult'].split('£')
            if adults != '0':
                value += f"\nAdult: {adults} (£{adult_value})"
        except Exception:
            pass

    if booking.get('Accompanying Senior'):
        try:
            seniors, senior_value = booking['Accompanying Senior'].split('£')
            if seniors != '0':
                value += f"\nSenior: {seniors} (£{senior_value})"
        except Exception:
            pass

    if booking.get('Custom fields prices') and 'age_of_child' in booking['Custom fields prices']:
        discounts = re.findall(r'-£([0-9.]+)', booking['Custom fields prices'])
        total_reduction = 0.0

        for discount in discounts:
            total_reduction += float(discount)

        original_price = re.findall(r'Child: [0-9]+ \(£([0-9.]+)\)', value)[0]
        new_price = float(original_price) - total_reduction
        value = re.sub(r'Child: ([0-9]+) \(£([0-9.]+)\)', f'Child: \\1 (£{new_price:.2f})', value)

    return value


def extract_present_details(value: str, booking: Dict[str, str]) -> str:
    genders = value.splitlines()
    gender_map: Dict[str, str] = dict([gender.split(':') for gender in genders])  # type: ignore

    ages = (
        booking['Child Age (Nov)'].splitlines()
        + booking['Child Age (Dec)'].splitlines()
        + booking.get('Child Age (Non-internet)', '').splitlines()
    )
    age_map: Dict[str, str] = dict([age.split(':') for age in ages])  # type: ignore

    age_symbols: Dict[str, str] = {}

    for idx, age in age_map.items():
        if 'to' in age and age.strip()[0] == '0':
            age_symbols[idx] = 'U1'
        else:
            age_symbols[idx] = age.split()[0]

    presents = []
    for idx in gender_map.keys():
        try:
            presents.append(f'{gender_map[idx][1]}{age_symbols[idx]}'.strip())
        except KeyError:
            presents.append(f'{gender_map[idx][1]}XX'.strip())
    return ', '.join(presents)


def parse_train_time(value: str, booking: Dict[str, str]) -> str:
    full_date_str = date_sort_item(value)
    return full_date_str.strftime('%H:%M')


def parse_train_date(value: str, booking: Dict[str, str]) -> str:
    full_date_str = date_sort_item(value)
    return full_date_str.strftime('%d/%m')


def remove_custom_price(value: str, booking: Dict[str, str]) -> str:
    val_str = value.split('£')[0]
    try:
        return str(int(val_str))
    except ValueError:
        if val_str == '':
            return '0'
        else:
            return 'ERR'


def include_additional_adults(value: str, booking: Dict[str, str], field='Adult'):
    value = remove_custom_price(value, booking)
    if 'Additional' in booking['Product title']:
        for ticket in booking['Price categories'].splitlines():
            ticket_fields = ticket.split()
            ticket_name = ticket_fields[0][:-1]
            ticket_qty = int(ticket_fields[1])

            if ticket_name == field:
                return str(ticket_qty)
        return '0'
    return value


def include_additional_seniors(value: str, booking: Dict[str, str]):
    return include_additional_adults(value, booking, field='Senior')


def remove_additional_adults(value: str, booking: Dict[str, str]):
    if 'Additional' in booking['Product title']:
        return '0'
    return value


TICKET_PRICES: Dict[str, Dict[str, Dict[str, float]]] = {}


def load_ticket_prices(ticket_prices: Dict[str, Dict[str, Dict[str, float]]]):
    global TICKET_PRICES
    TICKET_PRICES = ticket_prices


def calculate_walkin_price(value: str, booking: Dict[str, str]) -> str:
    value_clean = float(tidy_price(value, booking))
    if value_clean == 0.0:
        booking['walkin'] = 'true'
        try:
            date = date_sort_item(booking['Start date']).strftime('%d/%m/%y')
            event = booking['Product title']
            prices = TICKET_PRICES.get(
                f"{date} {event}",
                {'event': {}}
            )['event']

            walkin_price = 0.0

            # parse tickets
            for ticket in booking['Price categories'].splitlines():
                ticket_fields = ticket.split()
                name = ticket_fields[0][:-1]
                qty = int(ticket_fields[1])
                walkin_price += prices.get(name, 0.0) * qty

            # reduce infants
            infants = booking.get('Child Age (Non-internet)', '').count('to')
            infant_price = 6.0 if '11' == date.split('/')[1] else 7.0
            walkin_price -= infant_price * infants

            # include accompanying adults/seniors
            for extra, ticket in [
                ('Accompanying Adult', 'Adult'), ('Accompanying Senior', 'Senior')
            ]:
                try:
                    walkin_price += (
                        int(booking.get(extra, 0))
                        * prices.get(ticket, 0.0)
                    )
                except ValueError:
                    pass

            return f"{walkin_price:.2f}"

        except Exception:
            print('Walkin parsing failed')
    return f"{value_clean:.2f}"


## Output configuration ##
table_configuration = [
    # (<input column heading>, <output column label>, <optional conversion function>),
    ('Order ID', 'Order', None),
    ('Booking ID', 'Booking', None),
    ('Start date', 'Train', parse_train_time),
    ('Customer first name', 'First name', None),
    ('Customer last name', 'Last name', None),
    ('Quantity', 'Qty.', None),
    (None, 'Issued', None),
    (None, 'Infants', None),
    (None, 'QR?', None),
    ('Product price', 'Paid', tidy_price),
    ('Price categories', 'Price categories', include_custom_tickets),
    ('Present Type', 'Presents', extract_present_details)
]

column_sorts = {  # Use input column labels
    'Booking ID': 'ASC',
    'Order ID': 'ASC',
    'Start date': 'DATE',
}

GROUP_BOOKINGS_BY_DATE = True
BOOKING_FILTER_STRING = 'Day Rover'  # Only products containing this substring will be included in the output

# ===========================
## Internal logic ##


def parse_args():
    error_string = f'Usage: {sys.argv[0]} <input-csv-file> <output-csv-file>'

    if len(sys.argv) != 3:
        print(error_string)
        exit(1)

    if not (Path(sys.argv[1]).is_file()):
        print(error_string)
        exit(1)


def date_sort_item(date_str: str) -> datetime:
    value_clean = re.sub(r'([0-9]+)(st|nd|rd|th)', r'\1', date_str).replace(',', '')
    return datetime.strptime(value_clean, '%A %B %d %Y %I:%M %p')


def sort_bookings(bookings: List[List[str]], input_columns: List[str]) -> List[List[str]]:
    for sort_column, direction in column_sorts.items():
        try:
            sort_index = input_columns.index(sort_column)
        except ValueError:
            # Skip sorts by absent columns
            continue

        if direction == 'DATE':
            bookings.sort(key=lambda x: date_sort_item(x[sort_index]))
        else:
            try:
                bookings.sort(reverse=(direction == 'DESC'), key=lambda x: x[sort_index].lower())
            except AttributeError:
                bookings.sort(reverse=(direction == 'DESC'), key=lambda x: x[sort_index])

    return bookings


def filter_booking(booking: Dict[str, str]) -> bool:
    return (booking['Product title'].find(BOOKING_FILTER_STRING) != -1)


def format_booking_row(booking: Dict[str, str]) -> List[str]:
    booking_output = []

    for input_column, label, conversion in table_configuration:
        if input_column is None:
            booking_output.append('')
            continue

        field_value = booking[input_column]

        if conversion is not None:
            field_value = conversion(field_value, booking=booking)

        booking_output.append(field_value)

    return booking_output


def date_suffix(day: int) -> str:
    if 10 <= day <= 13:
        return 'th'
    else:
        return {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')


def format_group_date(date: datetime) -> str:
    day = date.day
    date_partial = date.strftime('%A %B')  # day of week & month

    return f"{date_partial} {day}{date_suffix(day)}".upper()


def main():
    output_bookings = []
    last_seen_date = datetime(1970, 1, 1, 0, 0)  # use minimum date so the first date in printed

    with open(sys.argv[1], 'r', errors='ignore') as f:
        data_list = list(csv.reader(f, delimiter=','))

        if not data_list:
            print("No CSV rows found")
            exit(1)

    labels = data_list[0]  # top row is labels

    bookings = sort_bookings(data_list[1:], labels)

    for row in bookings:
        booking = dict(zip(labels, row))  # map columns to label names
        if filter_booking(booking):
            output_bookings.append([format_booking_row(booking), booking])

    with open(sys.argv[2], 'w', newline='') as f:  # output data into a new csv
        output = csv.writer(f, quoting=csv.QUOTE_ALL)

        output.writerow([column[1] for column in table_configuration])  # write header row

        for booking, original_booking in output_bookings:
            if GROUP_BOOKINGS_BY_DATE:
                booking_date = date_sort_item(original_booking['Start date'])
                if booking_date != last_seen_date:
                    output.writerow(['', format_group_date(booking_date)])
                    last_seen_date = booking_date
            output.writerow(booking)


if __name__ == '__main__':
    parse_args()
    main()
