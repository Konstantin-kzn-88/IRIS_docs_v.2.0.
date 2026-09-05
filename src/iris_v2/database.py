from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event


def create_database_engine(database_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    return engine


def upgrade_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parent / "migrations")
    )
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path.as_posix()}")
    command.upgrade(config, "head")

