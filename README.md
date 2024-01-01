# Ticket Sheets

A flask website to process CSV dumps from the booking-activities wordpress plugin into printable tables

## Installation

The application uses gunicon to serve the flask app. To install the application, clone the repository and install the application using pip.

```bash
git clone https://github.com/WillB97/ticket-sheets
cd ticket-sheets
pip install .
```

Then install the application as a service using the provided systemd service file.

```bash
sudo cp ticket-sheets.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ticket-sheets
```

This will create a file called `config.json` and a folder called `flask_session` in the working directory, which is `/home/ubuntu/ticket-sheets/` by default.


## Development

To run the application in development mode, install the application using pip in editable mode.

```bash
git clone https://github.com/WillB97/ticket-sheets
cd ticket-sheets
python -m venv venv
source venv/bin/activate
pip install -e .
```

Then run the application using the `ticket_server` command to run the server in debug mode.
This will reload the server when changes are made to the source code.

```bash
ticket_server
```

This will create a file called `config.json` and a folder called `flask_session` in the current directory.
