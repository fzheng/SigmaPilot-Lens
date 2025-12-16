# Quick Start Guide

This guide covers detailed setup instructions for SigmaPilot Lens.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Deployment](#docker-deployment)
- [Local Development](#local-development)
- [Running Migrations](#running-migrations)
- [Testing the API](#testing-the-api)
- [WebSocket Testing](#websocket-testing)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### For Docker Deployment
- Docker Engine 20.10+
- Docker Compose 2.0+

### For Local Development
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- pip or poetry

## Docker Deployment

### 1. Clone and Configure

```bash
git clone https://github.com/fzheng/SigmaPilot-Lens.git
cd SigmaPilot-Lens

# Copy environment template
cp .env.example .env
```

### 2. Edit Configuration

Open `.env` and configure AI model API keys:

```bash
# Add AI model API keys (for Phase 2+)
MODEL_CHATGPT_API_KEY=sk-...
MODEL_GEMINI_API_KEY=...
MODEL_CLAUDE_API_KEY=sk-ant-...
MODEL_DEEPSEEK_API_KEY=...
```

**Note**: No API key authentication is required. SigmaPilot Lens uses network-level security - the API is only accessible from within the Docker network.

### 3. Start Services

```bash
# Start all services (gateway, worker, redis, postgres)
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f gateway
docker-compose logs -f worker
```

### 4. Run Database Migrations

```bash
docker-compose exec gateway alembic upgrade head
```

### 5. Verify Installation

```bash
# Health check
curl http://localhost:8000/api/v1/health

# Readiness check (verifies DB and Redis)
curl http://localhost:8000/api/v1/ready
```

## Local Development

### 1. Start Infrastructure

```bash
# Start only PostgreSQL and Redis
docker-compose up -d postgres redis
```

### 2. Set Up Python Environment

```bash
# Create virtual environment
python -m venv venv

# Activate (Linux/macOS)
source venv/bin/activate

# Activate (Windows)
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for testing
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your settings
```

### 4. Run Migrations

```bash
alembic upgrade head
```

### 5. Start the Application

```bash
# Start API server (with auto-reload)
uvicorn src.main:app --reload --port 8000

# In another terminal, start workers
python -m src.workers.main
```

## Running Migrations

### Create a New Migration

```bash
alembic revision --autogenerate -m "Description of changes"
```

### Apply Migrations

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade one step
alembic upgrade +1

# Downgrade one step
alembic downgrade -1

# Show current revision
alembic current
```

## Testing the API

### Access from Within Docker Network

The API is only accessible from within the Docker network. Use `docker-compose exec` to interact with the API:

```bash
# Health check
docker-compose exec gateway curl http://localhost:8000/api/v1/health

# Submit a test signal
docker-compose exec gateway curl -X POST http://localhost:8000/api/v1/signals \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "OPEN_SIGNAL",
    "symbol": "BTC-PERP",
    "signal_direction": "LONG",
    "entry_price": 50000.00,
    "size": 1.0,
    "liquidation_price": 45000.00,
    "ts_utc": "2025-01-15T10:30:00Z",
    "source": "test-signal"
  }'
```

Response:
```json
{
  "event_id": "uuid-here",
  "status": "ENQUEUED",
  "received_at": "2025-01-15T10:30:00.123Z"
}
```

### Check Queue Depth

```bash
curl http://localhost:8000/api/v1/queue/depth
```

### View Prometheus Metrics

```bash
curl http://localhost:8000/api/v1/metrics
```

## WebSocket Testing

WebSocket connections are also restricted to the Docker network.

### From a Container Connected to lens-network

```python
import asyncio
import websockets
import json

async def subscribe():
    # Connect to gateway from within Docker network
    uri = "ws://gateway:8000/api/v1/ws/stream"
    async with websockets.connect(uri) as ws:
        # Subscribe
        await ws.send(json.dumps({
            "action": "subscribe",
            "filters": {"symbol": "BTC-PERP"}
        }))

        # Listen for decisions
        while True:
            message = await ws.recv()
            decision = json.loads(message)
            print(f"Received: {decision}")

asyncio.run(subscribe())
```

### WebSocket Messages

```bash
# Subscribe to all decisions
{"action": "subscribe", "filters": {}}

# Subscribe with filters
{"action": "subscribe", "filters": {"symbol": "BTC-PERP", "model": "chatgpt"}}

# Ping/pong keepalive
{"type": "ping"}
{"type": "pong"}

# Unsubscribe
{"action": "unsubscribe"}
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs
docker-compose logs gateway
docker-compose logs worker

# Verify environment
docker-compose config
```

### Database Connection Failed

```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Test connection
docker-compose exec postgres psql -U lens -d lens -c "SELECT 1"
```

### Redis Connection Failed

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping
```

### Migration Errors

```bash
# Check current state
alembic current

# Show migration history
alembic history

# Reset database (DANGER: destroys data)
docker-compose down -v
docker-compose up -d postgres redis
alembic upgrade head
```

### Worker Not Processing

```bash
# Check worker logs
docker-compose logs -f worker

# Verify Redis streams
docker-compose exec redis redis-cli XLEN lens:signals:pending
docker-compose exec redis redis-cli XLEN lens:signals:enriched
```

## Next Steps

- Read the [API Reference](api-reference.md) for complete endpoint documentation
- Review [Data Contracts](data-contracts.md) for schema details
- See [Configuration Guide](configuration.md) for all options
- Check [Deployment Guide](deployment.md) for production setup
