import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_v1_router
from app.config import settings
from app.database import engine
from app.redis import close_redis, init_redis

# Configure Logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI Lifespan context manager for startup and shutdown events."""
    logger.info("Initializing WhatsApp OTP API SaaS Platform...")
    # Initialize Redis connection
    await init_redis()

    # Automatically create database tables if using SQLite for dev/testing
    if settings.DATABASE_URL.startswith("sqlite"):
        from app.database import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables verified.")

    yield

    logger.info("Shutting down platform...")
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Production-Grade WhatsApp OTP API SaaS Platform abstracting Meta Cloud API",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Calculates response time and logs HTTP requests."""
    start_time = time.time()
    response: Response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 2)

    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    logger.info(
        f"{request.method} {request.url.path} - Status: {response.status_code} - Latency: {duration_ms}ms"
    )
    return response


# Global Exception Handler for Unhandled Exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Unhandled Server Error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred. Please try again later.",
            }
        },
    )


# Include API v1 Router
app.include_router(api_v1_router)


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, str]:
    """Health check endpoint returning exact {"status": "ok"}."""
    return {"status": "ok"}
