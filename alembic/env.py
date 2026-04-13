"""Alembic environment — wires ATLAS models + sync URL from settings."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context  # type: ignore[attr-defined]
from sqlalchemy import engine_from_config, pool

from backend.config import get_settings
from backend.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):  # type: ignore[no-untyped-def]
    """Ignore JIP de_* tables — ATLAS only manages atlas_* schema."""
    if type_ == "table":
        if name.startswith("de_"):
            return False
        if name == "alembic_version":
            return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        version_table="atlas_alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            version_table="atlas_alembic_version",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
