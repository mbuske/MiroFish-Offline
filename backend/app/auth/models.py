"""ORM models for the auth store."""
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from .db import Base


ROLE_ADMIN = "admin"
ROLE_USER = "user"


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default=ROLE_USER)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=True)


class UserSession(Base):
    __tablename__ = "sessions"
    id = Column(String, primary_key=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_used_at = Column(DateTime, nullable=False)
    user_agent = Column(String, nullable=True)
    ip = Column(String, nullable=True)


class Branding(Base):
    __tablename__ = "branding"
    id = Column(String, primary_key=True)          # constant "singleton"
    primary_color = Column(String, nullable=True)
    accent_color = Column(String, nullable=True)
    logo_filename = Column(String, nullable=True)
    favicon_filename = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(String, nullable=True)
