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
# Add your AI API keys to .env

# Run
make build && make up && make migrate

# Verify
make health
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Quick Start](docs/quickstart.md) | Setup and first signal |
| [Architecture](docs/architecture.md) | System design |
| [API Reference](docs/api-reference.md) | Endpoints and schemas |
| [Configuration](docs/configuration.md) | Environment variables |

## License

Private repository. All rights reserved.
