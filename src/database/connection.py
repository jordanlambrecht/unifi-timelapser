#!/usr/bin/env python3
# src/database/connection.py
"""
Database connection and session management
"""

import os
import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from core.models import DatabaseSettings


from .models import Base

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database connections and sessions"""

    def __init__(self, settings: DatabaseSettings):
        self.settings = settings
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None

    @property
    def engine(self) -> Engine:
        """Get or create database engine"""
        if self._engine is None:
            self._engine = self._create_engine()
        return self._engine

    @property
    def session_factory(self) -> sessionmaker:
        """Get or create session factory"""
        if self._session_factory is None:
            self._session_factory = sessionmaker(bind=self.engine)
        return self._session_factory

    def _create_engine(self) -> Engine:
        """Create database engine with connection pooling"""
        logger.info(
            f"Creating database engine for {self.settings.host}:{self.settings.port}"
        )

        # Create engine with connection pooling
        engine = create_engine(
            self.settings.url,
            poolclass=QueuePool,
            pool_size=self.settings.pool_size,
            max_overflow=self.settings.max_overflow,
            pool_timeout=self.settings.pool_timeout,
            pool_recycle=self.settings.pool_recycle,
            echo=False,  # Set to True for SQL debugging
            future=True,
        )

        # Add connection event listeners
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """Set database-specific connection parameters"""
            if "postgresql" in str(engine.url):
                # PostgreSQL specific settings
                with dbapi_connection.cursor() as cursor:
                    cursor.execute("SET timezone = 'UTC'")

        return engine

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup"""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_all_tables(self):
        """Create all database tables"""
        logger.info("Creating database tables...")
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created successfully")

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.get_session() as session:
                from sqlalchemy import text

                session.execute(text("SELECT 1"))
            logger.info("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False

    def close(self):
        """Close database engine and all connections"""
        if self._engine:
            self._engine.dispose()
            logger.info("Database connections closed")


def create_database_manager(settings: DatabaseSettings) -> DatabaseManager:
    """Factory function to create database manager"""
    return DatabaseManager(settings)


def get_database_url_from_env() -> Optional[str]:
    """Get database URL from environment variables"""
    # Check for complete URL first
    if os.getenv("DATABASE_URL"):
        return os.getenv("DATABASE_URL")

    # Check for individual components
    host = os.getenv("TIMELAPSER_HOST", "localhost")
    port = os.getenv("TIMELAPSER_PORT", "5432")
    database = os.getenv("TIMELAPSER_DB", "timelapser")
    username = os.getenv("TIMELAPSER_USER", "timelapser")
    password = os.getenv("TIMELAPSER_PASS", "")

    if all([host, port, database, username]):
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"

    return None


def create_database_settings_from_env() -> DatabaseSettings:
    """Create database settings from environment variables"""
    database_url = get_database_url_from_env()

    if database_url:
        return DatabaseSettings(database_url=database_url)

    # Fallback to individual settings
    return DatabaseSettings(
        host=os.getenv("TIMELAPSER_HOST", "localhost"),
        port=int(os.getenv("TIMELAPSER_PORT", "5432")),
        database=os.getenv("TIMELAPSER_DB", "timelapser"),
        username=os.getenv("TIMELAPSER_USER", "timelapser"),
        password=os.getenv("TIMELAPSER_PASS", ""),
    )


# Global database manager instance
_db_manager: Optional[DatabaseManager] = None


def get_database_manager(
    settings: Optional[DatabaseSettings] = None,
) -> DatabaseManager:
    """Get or create the global database manager"""
    global _db_manager
    if _db_manager is None:
        if settings:
            _db_manager = DatabaseManager(settings)
        else:
            # Fallback to environment variables
            settings = create_database_settings_from_env()
            _db_manager = DatabaseManager(settings)
    return _db_manager


def get_db_session():
    """Get a database session (compatible with services.py)"""
    return get_database_manager().get_session()


def get_engine():
    """Get database engine (compatible with services.py)"""
    return get_database_manager().engine
