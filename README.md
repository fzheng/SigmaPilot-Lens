# SigmaPilot Lens

**Real-time Trading Signal Analysis Pipeline**

SigmaPilot Lens is a private, single-tenant module that ingests trading signals, enriches them with market data, evaluates them using multiple AI models (ChatGPT, Gemini, Claude, DeepSeek), and publishes follow/ignore recommendations via WebSocket.

> **Note**: SigmaPilot Lens does NOT place trades. It provides AI-powered analysis and recommendations only.

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

## License

Private repository. All rights reserved.

## Author

**fzheng** - [GitHub](https://github.com/fzheng)
