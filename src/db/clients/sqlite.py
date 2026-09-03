import logging
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy.engine.base import Engine
from sqlmodel import Session, SQLModel, create_engine

from constants import DIR_REPO
from db.clients.base import DbClient

logger = logging.getLogger(__name__)

SQLITE_DB_PATH = DIR_REPO.joinpath("sqlite.db")


class SqliteClient(DbClient):
    def __init__(self, sqlite_db_path: str = f"sqlite:///{SQLITE_DB_PATH}") -> None:
        self.engine: Engine = create_engine(sqlite_db_path)
        SQLModel.metadata.create_all(self.engine)
        # Databases created before the canonical flag existed need their chain
        # flags rebuilt once (see BlockRepository.rebuild_canonical_chain).
        self.needs_canonical_rebuild = self._migrate()

    def _migrate(self) -> bool:
        """Bring pre-existing tables up to the current schema.

        create_all only creates missing tables, so columns and indexes added to
        existing tables are applied here. Returns True if the block table gained
        the canonical column and its flags must be computed.
        """
        needs_rebuild = False
        with self.engine.begin() as connection:
            columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(block)")}
            if "canonical" not in columns:
                logger.info("Adding block.canonical column")
                connection.exec_driver_sql("ALTER TABLE block ADD COLUMN canonical BOOLEAN NOT NULL DEFAULT 0")
                needs_rebuild = True
            if "fork" in columns:
                logger.info("Dropping obsolete block.fork column")
                connection.exec_driver_sql("ALTER TABLE block DROP COLUMN fork")
            for table in SQLModel.metadata.sorted_tables:
                for index in table.indexes:
                    index.create(connection, checkfirst=True)
        return needs_rebuild

    def connect(self):
        pass

    @contextmanager
    def session(self) -> Iterator[Session]:
        with Session(self.engine) as connection:
            yield connection

    def disconnect(self):
        self.engine.dispose()
