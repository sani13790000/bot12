.PHONY: help build up down logs clean install dev

help:
	@echo "GalaxyVast Trading Bot - Development Commands"
	@echo ""
	@echo "Available commands:"
	@echo "  make install    - Install dependencies"
	@echo "  make build      - Build Docker images"
	@echo "  make up         - Start all services"
	@echo "  make down       - Stop all services"
	@echo "  make logs       - View service logs"
	@echo "  make clean      - Remove Docker containers and volumes"
	@echo "  make dev        - Start in development mode"

install:
	cd frontend && npm install
	pip install -r requirements.txt

build:
	docker-compose build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

clean:
	docker-compose down -v
	rm -rf node_modules
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

dev:
	docker-compose up --build

test:
	pytest backend/tests -v --tb=short

format:
	black backend
	isort backend

lint:
	flake8 backend
	pylint backend

type-check:
	mypy backend

all-checks: format lint type-check test
