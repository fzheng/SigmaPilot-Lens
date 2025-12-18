# SigmaPilot Lens

**AI-Powered Trading Signal Analysis Pipeline**

SigmaPilot Lens analyzes trading signals in real-time using multiple AI models and delivers actionable recommendations. It enriches incoming signals with live market data and technical indicators, then evaluates them through parallel AI analysis to produce follow/ignore decisions.

> **Note**: SigmaPilot Lens provides analysis only — it does NOT execute trades.

## What It Does

1. **Receives** trading signals from upstream strategies
2. **Enriches** with real-time market data and technical analysis
3. **Evaluates** using multiple AI models in parallel (ChatGPT, Gemini, Claude, DeepSeek)
4. **Delivers** recommendations via WebSocket streaming

## Key Capabilities

- **Multi-Model AI Consensus** — Get perspectives from 4 different AI providers simultaneously
- **Real-Time Enrichment** — Live market data from Hyperliquid with TA indicators
- **Signal Validation** — Automatic rejection of stale or price-drifted signals
- **Production Ready** — Load tested, observable, with comprehensive failure handling

## Quick Start

```bash
# Setup
cp .env.example .env
# Edit .env: set AUTH_MODE and configure tokens

# Run
make build && make up && make migrate

# Configure AI models via API (requires admin token)
curl -X PUT http://localhost:8000/api/v1/llm-configs/chatgpt \
  -H "Authorization: Bearer <your-admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-...", "enabled": true}'

# Verify
make health
```

## Authentication

SigmaPilot Lens supports 3 authentication modes:

| Mode | Use Case | Configuration |
|------|----------|---------------|
| `none` | Development | No auth required |
| `psk` | Docker Compose | Pre-shared key tokens |
| `jwt` | Production | External identity provider |

### Scopes

| Scope | Access |
|-------|--------|
| `lens:submit` | Submit signals |
| `lens:read` | Read events, decisions, DLQ |
| `lens:admin` | Admin operations + all above |

### PSK Mode Example

```bash
# .env
AUTH_MODE=psk
AUTH_TOKEN_SUBMIT=<generate-with-secrets.token_urlsafe(32)>
AUTH_TOKEN_READ=<generate-with-secrets.token_urlsafe(32)>
AUTH_TOKEN_ADMIN=<generate-with-secrets.token_urlsafe(32)>

# Usage
curl -X POST http://localhost:8000/api/v1/signals \
  -H "Authorization: Bearer <submit-token>" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC-PERP", ...}'
```

See [Configuration Guide](docs/configuration.md#authentication) for full details.

## Documentation

| Guide | Description |
|-------|-------------|
| [Quick Start](docs/quickstart.md) | Setup and first signal |
| [Architecture](docs/architecture.md) | System design |
| [API Reference](docs/api-reference.md) | Endpoints and schemas |
| [Configuration](docs/configuration.md) | Environment variables |

## License

Private repository. All rights reserved.
