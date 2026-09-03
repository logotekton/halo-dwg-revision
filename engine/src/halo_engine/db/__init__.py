"""SQLite persistence for one open project bundle (``docs/PLAN.md`` §4).

``models.py`` -- SQLAlchemy 2 ORM tables (file family only: project,
drawing_set, drawing_file, xref_link, entity_index; sheet/level/member
tables are P3). ``migrate.py`` -- runs this package's Alembic migrations
against a bundle's ``project.sqlite``. ``session.py`` -- per-bundle engine +
session factory. ``repos.py`` -- the only place that touches the ORM
directly. ``ids.py`` -- ULID primary keys.
"""
