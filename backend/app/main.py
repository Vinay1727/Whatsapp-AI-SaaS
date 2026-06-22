import logging

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import AppException
from app.db.mongodb import mongodb
from app.api.tenants import router as tenants_router
from app.api.sessions import router as sessions_router
from app.api.messages import router as messages_router
from app.api.webhook import router as webhook_router
from app.api.test_whatsapp import router as test_whatsapp_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mongodb.connect()
    logger.info("[STARTUP] MongoDB connected | db=%s", settings.mongodb_db_name)
    yield
    await mongodb.close()
    logger.info("[SHUTDOWN] MongoDB disconnected")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.message, "code": exc.code},
    )


@app.get("/health")
async def health():
    try:
        db = mongodb.get_db()
        await db.command("ping")
        db_ok = True
    except Exception:
        db_ok = False

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
    }


app.include_router(tenants_router)
app.include_router(sessions_router)
app.include_router(messages_router)
app.include_router(webhook_router)
app.include_router(test_whatsapp_router)
