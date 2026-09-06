import asyncio
import sqlite3
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_MIGRATIONS_DIRECTORY = Path(__file__).parent / "migrations"


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = self._create_engine(self.path)
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._initialize_lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        if self._initialized:
            return

        async with self._initialize_lock:
            if self._initialized:
                return

            async with self.engine.begin() as connection:
                await connection.exec_driver_sql(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migration (
                        version TEXT PRIMARY KEY,
                        applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                )

                for migration_path in sorted(_MIGRATIONS_DIRECTORY.glob("*.sql")):
                    version = migration_path.stem.split("_", maxsplit=1)[0]
                    result = await connection.execute(
                        text(
                            "SELECT version FROM schema_migration "
                            "WHERE version = :version"
                        ),
                        {"version": version},
                    )
                    if result.scalar_one_or_none() is not None:
                        continue

                    script = migration_path.read_text(encoding="utf-8")
                    for statement in _split_sql_script(script):
                        await connection.exec_driver_sql(statement)

                    await connection.execute(
                        text(
                            "INSERT INTO schema_migration (version) VALUES (:version)"
                        ),
                        {"version": version},
                    )

            self._initialized = True

    async def close(self) -> None:
        await self.engine.dispose()
        self._initialized = False

    @staticmethod
    def _create_engine(path: Path) -> AsyncEngine:
        engine = create_async_engine(URL.create("sqlite+aiosqlite", database=str(path)))

        @event.listens_for(engine.sync_engine, "connect")
        def configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys = ON")
                cursor.execute("PRAGMA journal_mode = WAL")
                cursor.execute("PRAGMA busy_timeout = 5000")
            finally:
                cursor.close()

        return engine

def is_healthy(self) -> bool:
    try:
        with self.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

def _split_sql_script(script: str) -> list[str]:
    statements: list[str] = []
    buffer = ""

    for line in script.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            if statement:
                statements.append(statement)
            buffer = ""

    if buffer.strip():
        raise ValueError("Migration SQL ends with an incomplete statement")

    return statements
