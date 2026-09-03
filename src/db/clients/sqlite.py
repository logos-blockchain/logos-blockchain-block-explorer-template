from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.engine.base import Engine
from sqlmodel import Session, SQLModel, create_engine

from constants import DIR_REPO
from db.clients.base import DbClient

SQLITE_DB_PATH = DIR_REPO.joinpath("sqlite.db")


class SqliteClient(DbClient):
    """No schema migrations: on a schema change, delete the database and let the explorer backfill from the node."""

    def __init__(self, sqlite_db_path: str = f"sqlite:///{SQLITE_DB_PATH}") -> None:
        self.engine: Engine = create_engine(sqlite_db_path)
        SQLModel.metadata.create_all(self.engine)

    def connect(self):
        pass

    @contextmanager
    def session(self) -> Iterator[Session]:
        with Session(self.engine) as connection:
            yield connection

    def disconnect(self):
        self.engine.dispose()
