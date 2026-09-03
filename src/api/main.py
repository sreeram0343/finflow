import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.config import settings
from src.core.database import init_db
from src.api.routes import ingest_router, review_router, ledger_router

# Logging setup
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
)
logger = logging.getLogger("finflow")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing FinFlow database schema...")
    await init_db()
    logger.info("FinFlow Engine startup completed successfully.")
    yield
    logger.info("Shutting down FinFlow Engine.")


app = FastAPI(
    title=settings.app_name,
    description="Multi-Agent Financial Document Ingestion, Reconciliation, and Compliance Engine",
    version="0.1.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(ingest_router, prefix="/api/v1")
app.include_router(review_router, prefix="/api/v1")
app.include_router(ledger_router, prefix="/api/v1")


@app.get("/health", tags=["System Health"])
async def health_check():
    """Health check endpoint for container orchestrators and load balancers."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.environment,
        "version": "0.1.0"
    }


@app.get("/", tags=["Root"])
async def root():
    """Root redirect / information endpoint."""
    return {
        "message": "Welcome to FinFlow Financial Processing Engine API.",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json"
    }
