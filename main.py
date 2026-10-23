"""
FastAPI main application.
Entry point for the Screenplay-to-Storyboard Generator.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.database import init_db
from backend import api

# Ensure runtime dirs exist before StaticFiles mounts (they are also created
# in Settings.__init__, but calling get_settings() here guarantees it)
_settings_pre = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Screenplay-to-Storyboard Generator")
    init_db()
    logger.info("Database initialized")
    yield
    # Shutdown
    logger.info("Shutting down")


# Create FastAPI application
app = FastAPI(
    title="Screenplay-to-Storyboard Generator",
    description="Convert screenplays into character-consistent storyboards",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api.router, prefix="/api")

# Serve static files (frontend)
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")
app.mount("/outputs", StaticFiles(directory=str(settings.output_dir)), name="outputs")

# Serve index.html at root
from fastapi.responses import FileResponse


@app.get("/")
async def root():
    """Serve the main frontend page."""
    index_path = settings.static_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Frontend not found. Please ensure static/index.html exists."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )
