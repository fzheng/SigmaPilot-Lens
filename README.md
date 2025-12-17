# SigmaPilot Lens

**Real-time Trading Signal Analysis Pipeline**

[![MVP Status](https://img.shields.io/badge/MVP-Complete-green.svg)](docs/implementation-plan.md)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Private-red.svg)](LICENSE)

SigmaPilot Lens is a private, single-tenant module that ingests trading signals, enriches them with market data, evaluates them using multiple AI models (ChatGPT, Gemini, Claude, DeepSeek), and publishes follow/ignore recommendations via WebSocket.

> **Note**: SigmaPilot Lens does NOT place trades. It provides AI-powered analysis and recommendations only.

## Features

- **Multi-Model AI Evaluation**: Parallel evaluation using 4 AI providers (OpenAI, Google, Anthropic, DeepSeek)
- **Real-time Market Enrichment**: Live data from Hyperliquid with technical analysis indicators
- **Signal Validation**: Early rejection of stale or price-drifted signals
- **WebSocket Streaming**: Real-time decision delivery with subscription filters
- **Dead Letter Queue**: Robust failure handling with retry and resolution workflows
- **Comprehensive Observability**: Prometheus metrics, structured logging, audit trails
- **Production Ready**: Resource limits, graceful shutdown, load tested for 60 signals/min

## Architecture

```
Signal → Queue → Enrichment → AI Evaluation → WebSocket
  │       │          │              │             │
  └───────┴──────────┴──────────────┴─────────────┘
                     │
                PostgreSQL (Audit)
```

## Security Model

SigmaPilot Lens uses **network-level security**:

- All services run inside an isolated Docker network (`lens-network`)
- **No ports are exposed to the host machine** - the API is only accessible from within the Docker network
- No API keys required - network isolation provides security
- External requests are rejected at the application level

This design is ideal for single-tenant deployments where the API is consumed by other containers in the same Docker network.

## Quick Start

### Prerequisites

- Docker & Docker Compose

### Run with Docker

```bash
# Clone and configure
git clone https://github.com/fzheng/SigmaPilot-Lens.git
cd SigmaPilot-Lens
cp .env.example .env
# Edit .env to add AI model API keys

# Build and start
make build
make up
make migrate
```

### Make Commands

| Command | Description |
|---------|-------------|
| `make build` | Build Docker images |
| `make rebuild` | Clean rebuild (removes volumes, builds, starts, migrates) |
| `make up` | Start all services |
| `make down` | Stop all services |
| `make logs` | Follow logs |
| `make test` | Run all tests |
| `make test-unit` | Run unit tests only |
| `make migrate` | Run database migrations |
| `make clean` | Remove all containers and volumes |

Or use docker-compose directly:

```bash
docker-compose up -d
docker-compose exec gateway alembic upgrade head
docker-compose logs -f
```

### Internal Access

The API is only accessible from within the Docker network:

```bash
# Health check (from host via docker exec)
docker-compose exec gateway curl http://localhost:8000/api/v1/health

# From another container on lens-network
curl http://gateway:8000/api/v1/health
```

## Usage

### Submit a Signal (from internal container)

```bash
# From a container connected to lens-network
curl -X POST http://gateway:8000/api/v1/signals \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "OPEN_SIGNAL",
    "symbol": "BTC-PERP",
    "signal_direction": "long",
    "entry_price": 50000.00,
    "size": 1.0,
    "ts_utc": "2025-01-15T10:30:00Z",
    "source": "my-strategy"
  }'
```

### Subscribe to Decisions (WebSocket)

```javascript
// From a client connected to the Docker network
const ws = new WebSocket('ws://gateway:8000/api/v1/ws/stream');

ws.onopen = () => {
  ws.send(JSON.stringify({
    action: 'subscribe',
    filters: { symbol: 'BTC-PERP' }  // optional filters
  }));
};

ws.onmessage = (event) => {
  const decision = JSON.parse(event.data);
  console.log(decision);
  // { decision: "FOLLOW_ENTER", confidence: 0.75, ... }
};
```

### Connect Another Service

To connect another container to the Lens network:

```yaml
# In your docker-compose.yml
services:
  my-service:
    image: my-image
    networks:
      - sigmapilot-lens_lens-network

networks:
  sigmapilot-lens_lens-network:
    external: true
```

## Configuration

Key settings in `.env`:

| Variable | Description |
|----------|-------------|
| `AI_MODELS` | Enabled models: `chatgpt,gemini,claude,deepseek` |
| `FEATURE_PROFILE` | Enrichment profile: `trend_follow_v1` |
| `DB_PASSWORD` | PostgreSQL password |

See [Configuration Guide](docs/configuration.md) for all options.

## Documentation

| Document | Description |
|----------|-------------|
| [Quick Start Guide](docs/quickstart.md) | Detailed setup instructions |
| [Architecture](docs/architecture.md) | System design and components |
| [API Reference](docs/api-reference.md) | Complete API documentation |
| [Data Contracts](docs/data-contracts.md) | Schema definitions |
| [Configuration](docs/configuration.md) | All configuration options |
| [Deployment](docs/deployment.md) | Production deployment guide |
| [Implementation Plan](docs/implementation-plan.md) | Development roadmap and status |

## Project Status

**MVP Complete** - All 5 phases implemented:

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | E2E Skeleton | ✅ Done |
| 2 | Signal Gateway | ✅ Done |
| 3 | Data Enrichment | ✅ Done |
| 4 | AI Evaluation | ✅ Done |
| 5 | Polish & Hardening | ✅ Done |

## License

Private repository. All rights reserved.

## Author

**fzheng** - [GitHub](https://github.com/fzheng)
