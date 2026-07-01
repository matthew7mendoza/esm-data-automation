"""
Database configuration & session management
"""
from collections.abc import AsyncGenerator
from importlib.resources import files
import os
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

__all__ = ["async_engine", "async_session_creator", "init_db_tables", "get_db_session"]

PROJECT_ROOT = Path(str(files("backend"))).parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "esm_form_automation.db"
DATABASE_URL: Final[str] = os.environ.get("DATABASE_URL", f"sqlite+aiosqlite///{DEFAULT_DB_PATH}")

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