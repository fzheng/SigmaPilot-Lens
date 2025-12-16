.PHONY: help build rebuild up down logs test test-unit test-cov migrate shell clean ps

# Default target
help:
	@echo "SigmaPilot Lens - Available commands:"
	@echo ""
	@echo "  make build      - Build Docker images"
	@echo "  make rebuild    - Clean rebuild (removes volumes)"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - Follow logs"
	@echo "  make ps         - Show running containers"
	@echo ""
	@echo "  make test       - Run all tests"
	@echo "  make test-unit  - Run unit tests only"
	@echo "  make test-cov   - Run tests with coverage"
	@echo ""
	@echo "  make migrate    - Run database migrations"
	@echo "  make shell      - Open shell in gateway container"
	@echo "  make clean      - Remove all containers and volumes"

# Build
build:
	docker-compose build

rebuild: clean build up migrate
	@echo "Rebuild complete!"

# Services
up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

ps:
	docker-compose ps

# Testing
test:
	docker-compose exec gateway pytest tests/ -v

test-unit:
	docker-compose exec gateway pytest tests/ -v -m "unit"

test-cov:
	docker-compose exec gateway pytest tests/ -v --cov=src --cov-report=term-missing

# Database
migrate:
	docker-compose exec gateway alembic upgrade head

# Development
shell:
	docker-compose exec gateway /bin/bash

# Cleanup
clean:
	docker-compose down -v --remove-orphans
