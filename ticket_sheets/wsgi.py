"""WSGI entrypoint."""

from .new_server import app

if __name__ == "__main__":
    app.run()
