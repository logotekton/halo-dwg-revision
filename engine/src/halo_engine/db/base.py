"""SQLAlchemy 2 declarative base, shared by every table in :mod:`halo_engine.db.models`."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Root of the ORM mapping. One physical database per project bundle (``project.sqlite``)."""


__all__ = ["Base"]
