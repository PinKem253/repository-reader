import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Track 4 muc 2: import SQLModel + toan bo model that cua project. Chi
# import thoi (khong dung truc tiep ten User/Repo/Conversation ben duoi)
# la DU -- moi lan 1 class table=True duoc dinh nghia, no tu dang ky
# chinh no vao SQLModel.metadata (bien global dung chung cho toan bo
# app). Neu thieu 1 import o day, autogenerate se KHONG thay bang do,
# tuong nham la bang "thua" can bi xoa.
from sqlmodel import SQLModel
from repository_reader.config import settings
from repository_reader.models import Conversation, Repo, User  # noqa: F401

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Track 4 muc 2: ghi de gia tri "sqlalchemy.url" tinh trong alembic.ini
# bang connection string THAT lay tu .env (cung 1 nguon voi db.py) --
# tranh phai dong bo tay DATABASE_URL o 2 noi (alembic.ini + .env) moi
# khi doi database (vd chuyen tu local sang Render).
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# Track 4 muc 2: tro ve metadata THAT cua SQLModel (thay vi None mac
# dinh) -- day la thu autogenerate se so sanh voi schema that trong DB.
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
