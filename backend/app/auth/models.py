"""ORM models for the auth store (expanded in Task 2)."""
from sqlalchemy import Column, String
from .db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True)
