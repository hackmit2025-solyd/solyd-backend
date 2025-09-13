#!/bin/bash

# Start docker services
echo "Starting Neo4j and PostgreSQL..."
docker-compose up -d

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 5

# Initialize Neo4j schema
echo "Initializing Neo4j schema..."
uv run python -m app.db.init_schema

# Start FastAPI server
echo "Starting FastAPI server..."
uv run fastapi dev app/main.py --host 0.0.0.0 --port 8000