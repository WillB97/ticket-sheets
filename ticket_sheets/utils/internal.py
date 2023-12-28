"""Internal functions."""

from typing import Dict, List

import pandas as pd


def categorise_presents(row: pd.Series, col_name: str) -> Dict[str, int]:
    """Count the number of children and infants."""
    presents: List[str] = row[col_name]
    # Filter to only infant tickets
    infant_presents = list(
        filter(lambda present: present in ["BU1", "B1", "GU1", "G1"], presents)
    )
    child_presents = list(filter(lambda present: present not in infant_presents, presents))

    return {"child_count": len(child_presents), "infant_count": len(infant_presents)}


def update_tickets(ticket_lines: List[str], ticket_name: str, new_val: int) -> None:
    """Update the ticket lines with the new value."""
    for idx, ticket_line in enumerate(ticket_lines):
        if ticket_line.startswith(f"{ticket_name}:"):
            ticket_lines[idx] = f"{ticket_name}: {new_val}"
            break
    else:
        ticket_lines.append(f"{ticket_name}: {new_val}")
