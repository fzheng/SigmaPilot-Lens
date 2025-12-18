"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.router import api_router
from src.core.network import InternalNetworkMiddleware
from src.core.config import settings
from src.core.rate_limit import init_rate_limiter
from src.models.database import close_db, init_db
from src.observability.logging import get_logger, setup_logging
from src.observability.metrics import metrics
from src.services.llm_config import get_llm_config_service
from src.services.queue import close_redis_client, get_redis_client, init_redis_client, reset_queue_producer

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    setup_logging()
    logger.info(f"Starting {settings.APP_NAME}")

    # Initialize database connection pool
    await init_db()
    logger.info("Database connection pool initialized")

    # Initialize Redis connection
    await init_redis_client()
    logger.info("Redis connection initialized")

    # Initialize rate limiter with Redis
    await init_rate_limiter(get_redis_client())
    logger.info(f"Rate limiter initialized (enabled={settings.RATE_LIMIT_ENABLED}, limit={settings.RATE_LIMIT_PER_MIN}/min)")

    # Initialize LLM config service (loads from database)
    llm_config_service = get_llm_config_service()
    await llm_config_service.initialize()
    enabled_models = await llm_config_service.get_enabled_models()
    logger.info(f"LLM config service initialized, enabled models: {enabled_models}")

    # Set application info metrics
    metrics.set_app_info(
        version="0.1.0",
        feature_profile=settings.FEATURE_PROFILE,
        ai_models=",".join(enabled_models) if enabled_models else "none",
    )

    logger.info(f"Feature profile: {settings.FEATURE_PROFILE}")
    logger.info(f"AI models (enabled): {enabled_models}")
    logger.info(f"WebSocket enabled: {settings.WS_ENABLED}")

    yield

    # Shutdown
    logger.info("Shutting down...")

    # Reset queue producer
    reset_queue_producer()

    # Close Redis connections
    await close_redis_client()
    logger.info("Redis connections closed")

    # Close database connections
    await close_db()
    logger.info("Database connections closed")

    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.APP_NAME,
    description="Real-time trading signal analysis pipeline with AI evaluation",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Internal network restriction middleware (must be added first - outermost)
app.add_middleware(InternalNetworkMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Only internal network can access anyway
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint with API info."""
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "ready": "/api/v1/ready",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
