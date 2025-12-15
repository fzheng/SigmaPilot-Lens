"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.router import api_router
from src.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown events."""
    # Startup
    # TODO: Initialize database connection pool
    # TODO: Initialize Redis connection
    # TODO: Start background workers if needed
    yield
    # Shutdown
    # TODO: Close database connections
    # TODO: Close Redis connections


app = FastAPI(
    title=settings.APP_NAME,
    description="Real-time trading signal analysis pipeline with AI evaluation",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """Liveness probe endpoint."""
    return {"status": "ok"}


@app.get("/ready")
async def readiness_check():
    """Readiness probe endpoint."""
    # TODO: Check database and Redis connectivity
    return {
        "status": "ready",
        "dependencies": {
            "redis": "ok",
            "postgres": "ok",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
    )
