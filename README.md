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

## Quick Start

### Prerequisites

- Docker & Docker Compose

### Run with Docker

```bash
# Clone and configure
git clone https://github.com/fzheng/SigmaPilot-Lens.git
cd SigmaPilot-Lens
cp .env.example .env
# Edit .env to set API_KEY_ADMIN and AI model API keys

# Start all services
docker-compose up -d

# Run migrations
docker-compose exec gateway alembic upgrade head

# View logs
docker-compose logs -f
```

### Access Points

| Service | URL |
|---------|-----|
| Swagger UI | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| Health Check | http://localhost:8000/api/v1/health |
| WebSocket | ws://localhost:8000/api/v1/ws/stream |

## Usage

### Submit a Signal

```bash
curl -X POST http://localhost:8000/api/v1/signals \
  -H "X-API-Key: YOUR_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "OPEN_SIGNAL",
    "symbol": "BTC-PERP",
    "signal_direction": "LONG",
    "entry_price": 50000.00,
    "size": 1.0,
    "liquidation_price": 45000.00,
    "ts_utc": "2025-01-15T10:30:00Z",
    "source": "my-strategy"
  }'
```

### Subscribe to Decisions (WebSocket)

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/stream?api_key=YOUR_KEY');

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

## Configuration

Key settings in `.env`:

| Variable | Description |
|----------|-------------|
| `API_KEY_ADMIN` | Admin API key (required) |
| `AI_MODELS` | Enabled models: `chatgpt,gemini,claude,deepseek` |
| `FEATURE_PROFILE` | Enrichment profile: `trend_follow_v1` |

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
