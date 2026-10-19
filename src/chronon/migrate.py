"""Entry point: ``python -m chronon.migrate`` (run by each initContainer)."""

from chronon.db import migrate

if __name__ == "__main__":
    migrate()
    print("schema is current")
