#!/bin/bash

pkill -f "fastapi dev"

echo "Stopping and removing Docker services..."
docker compose -f docker-compose-prod.yml down --volumes --remove-orphans

# Start docker services
echo "Starting Neo4j and PostgreSQL..."
docker compose -f docker-compose-prod.yml up -d

# Wait for services to be ready
echo "Waiting for services to be ready..."
sleep 5

# Initialize Neo4j schema
echo "Initializing Neo4j schema..."
uv run python -m app.db.init_schema

echo "Done!"