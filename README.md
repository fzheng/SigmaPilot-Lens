# SigmaPilot Lens

**Real-time Trading Signal Analysis Pipeline**

SigmaPilot Lens is a private, single-tenant module that ingests trading event signals, enriches them with market and technical analysis data, evaluates them using multiple AI models, and publishes follow/ignore recommendations in real time.

> ⚠️ **Important**: SigmaPilot Lens does NOT place trades. It provides AI-powered analysis and recommendations only.

## Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Signal    │───▶│    Queue    │───▶│ Enrichment  │───▶│     AI      │───▶│  Publisher  │
│   Gateway   │    │   (Redis)   │    │   Worker    │    │   Engine    │    │ (WebSocket) │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                                      │                  │                  │
      └──────────────────────────────────────┴──────────────────┴──────────────────┘
                                             │
                                    ┌─────────────────┐
                                    │   PostgreSQL    │
                                    │  (Audit/Store)  │
                                    └─────────────────┘
```

## Features

- **Signal Ingestion**: HTTP API for submitting trading signals with strict schema validation
- **Durable Queue**: Redis Streams with retry logic and dead letter queue (DLQ)
- **Data Enrichment**: Configurable feature packs with market data from Hyperliquid
- **Multi-Model AI Evaluation**: Parallel evaluation using ChatGPT, Gemini, and other models
- **Real-time Publishing**: WebSocket subscriptions filtered by model, symbol, or event type
- **Full Audit Trail**: End-to-end traceability with 180-day retention

## Quick Start

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Redis 7+
- PostgreSQL 15+

### Development Setup

```bash
# Clone the repository
git clone https://github.com/fzheng/SigmaPilot-Lens.git
cd SigmaPilot-Lens

# Copy environment template
cp .env.example .env

# Start infrastructure services
docker-compose up -d redis postgres

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start the application
python -m uvicorn src.main:app --reload
```

### Docker Deployment

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `API_KEY_ADMIN` | Admin key for key management | Required |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `FEATURE_PROFILE` | Feature pack for enrichment | `trend_follow_v1` |
| `AI_MODELS` | Comma-separated model list | `chatgpt,gemini` |
| `RATE_LIMIT_PER_MIN` | Rate limit per API key | `60` |

See [Configuration Guide](docs/configuration.md) for complete reference.

## API Overview

### Signal Ingestion

```bash
curl -X POST http://localhost:8000/api/v1/signals \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "OPEN_SIGNAL",
    "symbol": "BTC",
    "signal_direction": "long",
    "entry_price": 42000.00,
    "size": 0.1,
    "liquidation_price": 38000.00,
    "ts_utc": "2024-01-15T10:30:00Z",
    "source": "strategy_alpha"
  }'
```

### WebSocket Subscription

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/decisions?api_key=your-key');

// Subscribe to specific filters
ws.send(JSON.stringify({
  action: 'subscribe',
  filters: { model: 'chatgpt', symbol: 'BTC' }
}));

// Receive decisions
ws.onmessage = (event) => {
  const decision = JSON.parse(event.data);
  console.log(decision);
};
```

## Documentation

- [Architecture Overview](docs/architecture.md)
- [Implementation Plan](docs/implementation-plan.md)
- [API Reference](docs/api-reference.md)
- [Data Contracts](docs/data-contracts.md)
- [Configuration Guide](docs/configuration.md)
- [Deployment Guide](docs/deployment.md)

## Project Structure

```
SigmaPilot-Lens/
├── src/
│   ├── api/              # FastAPI routes and endpoints
│   ├── core/             # Core configuration and utilities
│   ├── models/           # SQLAlchemy and Pydantic models
│   ├── services/         # Business logic services
│   │   ├── enrichment/   # Data enrichment workers
│   │   ├── evaluation/   # AI model evaluation
│   │   ├── providers/    # Market data providers
│   │   └── queue/        # Redis queue management
│   ├── websocket/        # WebSocket handlers
│   └── main.py           # Application entry point
├── prompts/              # AI model prompt templates
├── config/               # Configuration files
├── migrations/           # Alembic database migrations
├── tests/                # Test suite
├── docs/                 # Documentation
└── docker-compose.yml    # Docker orchestration
```

## Performance Targets (MVP)

| Metric | Target |
|--------|--------|
| End-to-end latency (p95) | < 6 seconds |
| Enrichment latency (p95) | < 2 seconds |
| Model evaluation (p95) | < 3 seconds per model |
| WebSocket fanout (p95) | < 1 second |
| DLQ rate | < 1% |

## License

Private repository. All rights reserved.

## Author

**fzheng** - [GitHub](https://github.com/fzheng)
