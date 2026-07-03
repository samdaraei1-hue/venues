from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from .config import AppConfig
from .models import Base


def build_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    url = make_url(database_url)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, echo=False, future=True, connect_args=connect_args, pool_pre_ping=True)


def build_session_factory(database_url: str):
    engine = build_engine(database_url)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True), engine


def init_db(database_url: str) -> None:
    _, engine = build_session_factory(database_url)
    Base.metadata.create_all(engine)


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
    init_db(config.database_url)
