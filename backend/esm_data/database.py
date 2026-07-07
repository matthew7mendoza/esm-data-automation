"""
Database configuration & session management
"""

import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Final

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

__all__ = ["async_engine", "async_session_creator", "get_db_session", "init_db_tables"]

PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "esm_form_automation.db"
DATABASE_URL: Final[str] = os.environ.get(
    "DATABASE_URL", f"sqlite+aiosqlite:///{DEFAULT_DB_PATH}"
)

async_engine: AsyncEngine = create_async_engine(DATABASE_URL, echo=False, future=True)
async_session_creator: async_sessionmaker[AsyncSession] = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db_tables() -> None:
    """
    Build database table schema if missing on startup
    """

    async with async_engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    provides temporary db connection for request,
    safely closes when finished
    """

    async with async_session_creator() as session:
        yield session
