"""SQLAlchemy engine/session factory for the auth store (SQLite)."""
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

_engine = None
SessionLocal = sessionmaker(autoflush=False, autocommit=False)


def get_engine(db_path):
    global _engine
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
        future=True,
    )
    SessionLocal.configure(bind=_engine)
    return _engine


def init_db(db_path):
    """Create the engine and all tables. Idempotent."""
    engine = get_engine(db_path)
    # Import models so they register on Base before create_all.
    from . import models  # noqa: F401
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
