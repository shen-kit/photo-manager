from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from alembic.operations import ops
from sqlalchemy import engine_from_config
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from app import models as app_models  # noqa: F401
from app.core.database import DATABASE_URL

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = SQLModel.metadata


def render_item(type_: str, obj, autogen_context):
    if type_ == "type":
        if isinstance(obj, app_models.Vector):
            autogen_context.imports.add("from app import models as app_models")
            return f"app_models.Vector({obj.dimensions})"
        if isinstance(obj, app_models.Ltree):
            autogen_context.imports.add("from app import models as app_models")
            return "app_models.Ltree()"
    return False


def process_revision_directives(context, revision, directives) -> None:
    if not getattr(config.cmd_opts, "autogenerate", False):
        return

    script = directives[0]
    if script.upgrade_ops.is_empty():
        directives[:] = []
        print("No schema changes detected.")


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=render_item,
        process_revision_directives=process_revision_directives,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_item=render_item,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
