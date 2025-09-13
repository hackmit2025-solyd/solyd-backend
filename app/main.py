from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.db.neo4j import Neo4jConnection
from app.db.database import init_db
from app.api import graph, chat, visualization, ingest


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Medical Knowledge Graph Backend...")

    # Initialize PostgreSQL database (optional - won't fail if DB is not available)
    try:
        init_db()
        print("PostgreSQL database initialized successfully")
    except Exception as e:
        print(f"Warning: PostgreSQL initialization failed: {e}")
        print("Continuing without PostgreSQL support...")

    # Initialize Neo4j connection
    neo4j_conn = Neo4jConnection()
    app.state.neo4j = neo4j_conn

    yield

    # Shutdown
    print("Shutting down...")
    neo4j_conn.close()


app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(
    visualization.router, prefix="/api/visualization", tags=["Visualization"]
)
app.include_router(ingest.router, prefix="/api/ingest", tags=["Ingest"])


@app.get("/")
def root():
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}
