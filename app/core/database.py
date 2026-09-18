"""
Database connection and session management.

AGPL-3.0 License - See LICENSE file for details.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings

# Create the Engine (connection pool)
engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI),
    pool_pre_ping=True  # Auto-reconnect if DB connection drops
)

# Create the Session Factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Base class for all models
class Base(DeclarativeBase):
    pass


def get_db():
    """
    Database session generator.
    Use in Celery tasks: db = SessionLocal()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
