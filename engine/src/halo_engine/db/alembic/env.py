"""Alembic environment, driven programmatically by :mod:`halo_engine.db.migrate`.

No ``alembic.ini`` on disk: :func:`halo_engine.db.migrate.upgrade_to_head`
builds the :class:`alembic.config.Config` in memory (``script_location`` +
``sqlalchemy.url`` only) and calls ``alembic.command.upgrade`` directly, once
per bundle's own ``project.sqlite``. That keeps every migration-related file
under this task's owned ``db/**`` glob.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from halo_engine.db import models  # noqa: F401  (registers every table on Base.metadata)
from halo_engine.db.base import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # halo_engine.db.migrate never sets this attribute today (it lets us
    # build the engine here from sqlalchemy.url instead), but honouring it
    # keeps this env.py reusable from a caller that already holds an open
    # Connection (e.g. a future test harness) without editing it again.
    connectable = config.attributes.get("connection")
    if connectable is not None:
        context.configure(connection=connectable, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = engine_from_config(
        config.get_section(config.config_ini_section) or {},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
