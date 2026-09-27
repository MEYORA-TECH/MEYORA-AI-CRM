import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import ai, api_keys, auth, crm, emails, integrations, memories, organizations, research
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.database.session import engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    stop = asyncio.Event()
    task = None
    if settings.jobs_worker_enabled:
        from app.jobs.worker import worker_loop

        task = asyncio.create_task(worker_loop(stop))
    yield
    stop.set()
    if task:
        await task


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(json_logs=settings.is_production)

    app = FastAPI(
        title="Meyora API",
        version="0.1.0",
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
        lifespan=lifespan,
    )
    register_error_handlers(app)

    app.add_middleware(RequestContextMiddleware, hsts=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    api = APIRouter(prefix="/api")

    @api.get("/health", tags=["health"])
    async def health():
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}

    api.include_router(auth.router)
    api.include_router(organizations.router)
    api.include_router(api_keys.router)
    api.include_router(crm.router)
    api.include_router(ai.router)
    api.include_router(memories.router)
    api.include_router(integrations.router)
    api.include_router(emails.router)
    api.include_router(research.router)
    app.include_router(api)
    return app


app = create_app()
