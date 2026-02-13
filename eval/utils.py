"""Shared utilities for the eval framework.

DSN construction and parsing used by both the original search eval
and the benchmark eval.
"""

import os


def build_admin_dsn() -> str:
    """Build admin DSN from environment or defaults.

    The admin DSN connects to the 'postgres' database for CREATE/DROP DATABASE.
    """
    host = os.getenv("CAIRN_DB_HOST", "localhost")
    port = os.getenv("CAIRN_DB_PORT", "5432")
    user = os.getenv("CAIRN_DB_USER", "cairn")
    password = os.getenv("CAIRN_DB_PASS", "cairn")
    return f"postgresql://{user}:{password}@{host}:{port}/postgres"


def replace_dbname(dsn: str, new_dbname: str) -> str:
    """Replace the database name in a PostgreSQL DSN.

    Handles: postgresql://user:pass@host:port/olddb -> .../newdb
    """
    base = dsn.rsplit("/", 1)[0]
    return f"{base}/{new_dbname}"
