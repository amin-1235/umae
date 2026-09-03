"""Database connection and session management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from umae.storage.models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager."""

    def __init__(self, database_url: str | None = None) -> None:
        """Initialize database connection.

        Args:
            database_url: Database URL (defaults to SQLite)
        """
        if database_url is None:
            # Default to SQLite in the project directory
            db_path = Path("data") / "umae.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{db_path}"

        self.database_url = database_url
        self._engine: Engine | None = None
        self._session_factory: sessionmaker[Session] | None = None

    @property
    def engine(self) -> Engine:
        """Get or create database engine."""
        if self._engine is None:
            self._engine = create_engine(
                self.database_url,
                echo=False,
                pool_pre_ping=True,
            )

            # Enable WAL mode for SQLite
            if "sqlite" in self.database_url:

                @event.listens_for(self._engine, "connect")
                def set_sqlite_pragma(dbapi_connection: object, connection_record: object) -> None:
                    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA foreign_keys=ON")
                    cursor.close()

        return self._engine

    @property
    def session_factory(self) -> sessionmaker[Session]:
        """Get or create session factory."""
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory

    def create_tables(self) -> None:
        """Create all tables."""
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created")

    def drop_tables(self) -> None:
        """Drop all tables (use with caution)."""
        Base.metadata.drop_all(self.engine)
        logger.warning("Database tables dropped")

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.session_factory()

    def close(self) -> None:
        """Close database connections."""
        if self._engine:
            self._engine.dispose()
            logger.info("Database connections closed")


# Global database instance
_db: Database | None = None


def get_database() -> Database:
    """Get global database instance."""
    global _db
    if _db is None:
        _db = Database()
        _db.create_tables()
    return _db


def init_database(database_url: str) -> Database:
    """Initialize database with custom URL.

    Args:
        database_url: Database URL

    Returns:
        Database instance
    """
    global _db
    _db = Database(database_url)
    _db.create_tables()
    return _db


def get_session() -> Session:
    """Get a database session (convenience function)."""
    return get_database().get_session()
