from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn
import logging
from app.api import auth, chat, documents, projects, workflows, agent, memory
from app.db import create_db_and_tables
from app.core.config import settings
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("astra-os")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("🚀 ASTRA OS starting up...")
    create_db_and_tables()

    # Pre-warm Ollama connection check
    from app.services.ollama import ollama_service
    healthy = await ollama_service.health_check()
    if healthy:
        logger.info(f"✅ Ollama connected — default model ready")
    else:
        logger.warning("⚠️  Ollama not reachable or model not found. Run: ollama serve")

    yield

    # Shutdown: close HTTP client pools
    from app.services.ollama import _http_client
    from app.services.document_service import document_service
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
    await document_service.close()
    
    logger.info("🛑 ASTRA OS shut down.")


app = FastAPI(
    title="ASTRA OS API",
    description="The Orchestration Engine for Astra AI OS",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow configured frontend origins
# Astra-Fix: Explicitly allow both localhost and 127.0.0.1 to prevent CORS blocks
# Now using centralized settings for consistency.
allowed_origins_raw = settings.ALLOWED_ORIGINS
# Strip any leading/trailing quotes that might be in the .env file
allowed_origins_raw = allowed_origins_raw.strip('"').strip("'")
allowed_origins = [
    o.strip() for o in allowed_origins_raw.split(",") if o.strip()
]
logger.info(f"🛡️  CORS Origins: {allowed_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/api/v1", tags=["Chat"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])
app.include_router(projects.router, prefix="/api/v1/projects", tags=["Projects"])
app.include_router(workflows.router, prefix="/api/v1/workflows", tags=["Workflows"])
app.include_router(agent.router, prefix="/api/v1/agent", tags=["Agent"])
app.include_router(memory.router, prefix="/api/v1/memory", tags=["Memory"])


@app.get("/")
async def root():
    return {
        "status": "online",
        "system": "ASTRA OS",
        "engine": "FastAPI",
        "message": "Orchestration Layer Ready",
    }


@app.get("/health")
async def health_check():
    """Health check with Ollama status."""
    from app.services.ollama import ollama_service
    ollama_ok = await ollama_service.health_check()
    return {
        "status": "healthy",
        "ollama": "connected" if ollama_ok else "disconnected",
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
