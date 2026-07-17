from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
import threading

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import AppConfig
from .models import Base


_ENGINE_LOCK = threading.Lock()
_INIT_DONE = False


def build_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, echo=False, future=True, connect_args=connect_args, pool_pre_ping=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return (
        sessionmaker(
            bind=engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            future=True,
        ),
        engine,
    )


def _ping_engine(engine) -> None:
    # Lightweight connectivity check; fails fast with better diagnostics.
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def init_db(database_url: str) -> None:
    _, engine = build_session_factory(database_url)
    _ping_engine(engine)
    Base.metadata.create_all(engine)
    # create_all does not add columns to an existing installation. Keep this
    # tiny migration here so upgrades work without a separate migration tool.
    columns = {column["name"] for column in inspect(engine).get_columns("venues")}
    if "is_hidden" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE venues ADD COLUMN is_hidden BOOLEAN NOT NULL DEFAULT FALSE"))


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    factory, engine = build_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        engine.dispose()


def init_from_config(config: AppConfig) -> None:
    global _INIT_DONE
    if _INIT_DONE:
        return

    with _ENGINE_LOCK:
        if _INIT_DONE:
            return
        init_db(config.database_url)
        _INIT_DONE = True
