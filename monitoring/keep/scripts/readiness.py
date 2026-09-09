"""Check the HTTP worker and its database without changing application state."""
import os
import sys
from urllib.request import urlopen

import psycopg2
from sqlalchemy.engine import make_url


def check_ready():
    with urlopen("http://127.0.0.1:8080/healthcheck", timeout=1) as response:
        if response.status != 200:
            return False
    url = make_url(os.environ["DATABASE_CONNECTION_STRING"])
    connection = psycopg2.connect(
        host=url.host, port=url.port or 5432, dbname=url.database,
        user=url.username, password=url.password, connect_timeout=2,
        options="-c statement_timeout=1000 -c default_transaction_read_only=on",
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            return cursor.fetchone() == (1,)
    finally:
        connection.close()


if __name__ == "__main__":
    try:
        ready = check_ready()
    except Exception:
        # Driver errors can contain connection credentials; never print their details.
        ready = False
    sys.exit(0 if ready else 1)
