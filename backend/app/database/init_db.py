"""Create the database file and tables: python -m app.database.init_db"""
from ..config import get_settings
from .db import Database

if __name__ == "__main__":
    s = get_settings()
    s.ensure_dirs()
    Database(s.db_path).init()
    print(f"Database ready: {s.db_path}")
