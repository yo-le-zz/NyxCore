"""NyxCore Server — main entry point."""

from __future__ import annotations

import argparse
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from src.server.core.config import settings
from src.server.core.database import init_db
from src.server.middleware.rate_limit import RateLimitMiddleware
from src.server.middleware.security import SecurityHeadersMiddleware
from src.server.routers import admin, auth, health, isos, licenses, machines

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nyxcore.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("NyxCore Server starting — initialising database …")
    await init_db()
    logger.info(f"Server ready on port {settings.PORT}")
    yield
    logger.info("NyxCore Server shutting down.")


app = FastAPI(
    title="NyxCore API",
    version="1.0.0",
    description="ISO/OS HUB platform — secure REST API",
    docs_url="/api/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Middlewares ────────────────────────────────────────────────────────────────
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, calls=60, period=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routers ────────────────────────────────────────────────────────────────
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(licenses.router, prefix="/api/v1/licenses", tags=["licenses"])
app.include_router(machines.router, prefix="/api/v1/machines", tags=["machines"])
app.include_router(isos.router, prefix="/api/v1/isos", tags=["isos"])

# ── Admin web panel + REST under /admin ───────────────────────────────────────
app.include_router(admin.router, prefix="/admin", tags=["admin"])


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/admin/")


def run():
    parser = argparse.ArgumentParser(description="NyxCore Server")
    parser.add_argument("--port", type=int, default=settings.PORT)
    parser.add_argument("--host", type=str, default=settings.HOST)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()

    uvicorn.run(
        "src.server.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        access_log=True,
        log_level="info",
    )


if __name__ == "__main__":
    run()
