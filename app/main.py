from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.dependencies import get_database
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.logging import configure_logging

load_dotenv()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    database = get_database()
    await database.initialize()
    try:
        yield
    finally:
        await database.close()


def create_app() -> FastAPI:
    configure_logging()

    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        debug=settings.app_debug,
        lifespan=lifespan,
    )

    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
