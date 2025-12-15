# API Reference

Base URL: `http://localhost:8000/api/v1`

All endpoints require authentication via the `X-API-Key` header unless otherwise noted.

---

## Authentication

All API requests must include an API key:

```
X-API-Key: your-api-key
```

Admin endpoints require an admin API key (configured via `API_KEY_ADMIN` environment variable).

---

## Signals

### Submit Signal

Submit a trading signal for analysis.

```
POST /signals
```

**Headers**:
| Header | Required | Description |
|--------|----------|-------------|
| `X-API-Key` | Yes | API key |
| `Content-Type` | Yes | `application/json` |

**Request Body**:
```json
{
  "event_type": "OPEN_SIGNAL",
  "symbol": "BTC",
  "signal_direction": "long",
  "entry_price": 42000.50,
  "size": 0.1,
  "liquidation_price": 38000.00,
  "ts_utc": "2024-01-15T10:30:00Z",
  "source": "strategy_alpha"
}
```

**Response** `201 Created`:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ENQUEUED",
  "received_at": "2024-01-15T10:30:00.123Z"
}
```

**Error Responses**:

`400 Bad Request` - Invalid schema:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request body",
    "details": [
      { "field": "entry_price", "message": "must be greater than 0" }
    ]
  }
}
```

`401 Unauthorized` - Invalid API key:
```json
{
  "error": {
    "code": "UNAUTHORIZED",
    "message": "Invalid or missing API key"
  }
}
```

`429 Too Many Requests` - Rate limited:
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded",
    "retry_after": 45
  }
}
```

---

## Events

### List Events

Retrieve a list of submitted events.

```
GET /events
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | - | Filter by symbol |
| `event_type` | string | - | Filter by event type |
| `source` | string | - | Filter by source |
| `since` | datetime | - | Events after this time |
| `until` | datetime | - | Events before this time |
| `status` | string | - | Filter by status |
| `limit` | int | 50 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "event_type": "OPEN_SIGNAL",
      "symbol": "BTC",
      "signal_direction": "long",
      "entry_price": 42000.50,
      "size": 0.1,
      "status": "PUBLISHED",
      "source": "strategy_alpha",
      "received_at": "2024-01-15T10:30:00.123Z"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

### Get Event

Retrieve a specific event with full details.

```
GET /events/{event_id}
```

**Response** `200 OK`:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "OPEN_SIGNAL",
  "symbol": "BTC",
  "signal_direction": "long",
  "entry_price": 42000.50,
  "size": 0.1,
  "liquidation_price": 38000.00,
  "ts_utc": "2024-01-15T10:30:00Z",
  "source": "strategy_alpha",
  "received_at": "2024-01-15T10:30:00.123Z",
  "status": "PUBLISHED",
  "timeline": [
    { "status": "RECEIVED", "timestamp": "2024-01-15T10:30:00.123Z" },
    { "status": "ENQUEUED", "timestamp": "2024-01-15T10:30:00.125Z" },
    { "status": "ENRICHED", "timestamp": "2024-01-15T10:30:01.850Z" },
    { "status": "MODEL_DONE", "timestamp": "2024-01-15T10:30:04.200Z", "details": { "model": "chatgpt" } },
    { "status": "MODEL_DONE", "timestamp": "2024-01-15T10:30:04.500Z", "details": { "model": "gemini" } },
    { "status": "PUBLISHED", "timestamp": "2024-01-15T10:30:04.510Z" }
  ],
  "enriched": {
    "feature_profile": "trend_follow_v1",
    "quality_flags": {
      "missing_data": [],
      "stale_data": [],
      "provider_errors": []
    }
  },
  "decisions": [
    {
      "model": "chatgpt",
      "decision": "FOLLOW_ENTER",
      "confidence": 0.78
    },
    {
      "model": "gemini",
      "decision": "FOLLOW_ENTER",
      "confidence": 0.72
    }
  ]
}
```

**Error Response** `404 Not Found`:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Event not found"
  }
}
```

### Get Event Status

Get the current processing status of an event.

```
GET /events/{event_id}/status
```

**Response** `200 OK`:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PUBLISHED",
  "current_stage": "COMPLETE",
  "duration_ms": 4387
}
```

---

## Decisions

### List Decisions

Query AI model decisions.

```
GET /decisions
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | - | Filter by model name |
| `symbol` | string | - | Filter by symbol |
| `event_type` | string | - | Filter by event type |
| `decision` | string | - | Filter by decision |
| `min_confidence` | float | - | Minimum confidence |
| `since` | datetime | - | Decisions after this time |
| `until` | datetime | - | Decisions before this time |
| `limit` | int | 50 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": "dec-001",
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "symbol": "BTC",
      "event_type": "OPEN_SIGNAL",
      "model": "chatgpt",
      "decision": "FOLLOW_ENTER",
      "confidence": 0.78,
      "entry_plan": { "type": "limit", "offset_bps": -5 },
      "risk_plan": { "stop_method": "atr", "atr_multiple": 2.0 },
      "size_pct": 15,
      "reasons": ["bullish_ema_alignment", "positive_macd_crossover"],
      "evaluated_at": "2024-01-15T10:30:04.200Z"
    }
  ],
  "total": 500,
  "limit": 50,
  "offset": 0
}
```

### Get Decision

Get a specific decision by ID.

```
GET /decisions/{decision_id}
```

**Response** `200 OK`:
```json
{
  "id": "dec-001",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTC",
  "event_type": "OPEN_SIGNAL",
  "model": "chatgpt",
  "decision": "FOLLOW_ENTER",
  "confidence": 0.78,
  "entry_plan": { "type": "limit", "offset_bps": -5 },
  "risk_plan": { "stop_method": "atr", "atr_multiple": 2.0 },
  "size_pct": 15,
  "reasons": ["bullish_ema_alignment", "positive_macd_crossover"],
  "model_meta": {
    "model_name": "chatgpt",
    "model_version": "gpt-4o",
    "latency_ms": 1850,
    "status": "SUCCESS",
    "tokens_used": 1250
  },
  "evaluated_at": "2024-01-15T10:30:04.200Z"
}
```

---

## API Keys (Admin)

These endpoints require the admin API key.

### Create API Key

Create a new API key.

```
POST /keys
```

**Request Body**:
```json
{
  "name": "executor-1",
  "expires_at": "2025-01-15T00:00:00Z"
}
```

**Response** `201 Created`:
```json
{
  "id": "key-001",
  "name": "executor-1",
  "key": "lens_k1_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "key_prefix": "lens_k1_",
  "expires_at": "2025-01-15T00:00:00Z",
  "created_at": "2024-01-15T10:30:00Z"
}
```

> **Note**: The full `key` is only returned on creation. Store it securely.

### List API Keys

List all API keys.

```
GET /keys
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_expired` | bool | false | Include expired keys |
| `include_deleted` | bool | false | Include deleted keys |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": "key-001",
      "name": "executor-1",
      "key_prefix": "lens_k1_",
      "is_admin": false,
      "expires_at": "2025-01-15T00:00:00Z",
      "created_at": "2024-01-15T10:30:00Z",
      "deleted_at": null
    }
  ]
}
```

### Get API Key

Get details of a specific API key.

```
GET /keys/{key_id}
```

**Response** `200 OK`:
```json
{
  "id": "key-001",
  "name": "executor-1",
  "key_prefix": "lens_k1_",
  "is_admin": false,
  "expires_at": "2025-01-15T00:00:00Z",
  "created_at": "2024-01-15T10:30:00Z",
  "deleted_at": null,
  "usage": {
    "requests_24h": 150,
    "last_used_at": "2024-01-15T10:29:00Z"
  }
}
```

### Delete API Key

Revoke an API key.

```
DELETE /keys/{key_id}
```

**Response** `204 No Content`

---

## Dead Letter Queue (Admin)

### List DLQ Entries

List failed processing entries.

```
GET /dlq
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stage` | string | - | Filter by stage (ENRICHMENT, EVALUATION) |
| `error_code` | string | - | Filter by error code |
| `since` | datetime | - | Entries after this time |
| `limit` | int | 50 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": "dlq-001",
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "stage": "ENRICHMENT",
      "error_code": "PROVIDER_ERROR",
      "error_message": "Hyperliquid API returned 503",
      "retry_count": 5,
      "created_at": "2024-01-15T10:30:15.000Z"
    }
  ],
  "total": 5,
  "limit": 50,
  "offset": 0
}
```

### Get DLQ Entry

Get details of a DLQ entry including full payload.

```
GET /dlq/{dlq_id}
```

**Response** `200 OK`:
```json
{
  "id": "dlq-001",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "stage": "ENRICHMENT",
  "error_code": "PROVIDER_ERROR",
  "error_message": "Hyperliquid API returned 503",
  "payload": { /* original message */ },
  "retry_count": 5,
  "created_at": "2024-01-15T10:30:15.000Z"
}
```

### Retry DLQ Entry

Retry processing a DLQ entry.

```
POST /dlq/{dlq_id}/retry
```

**Response** `202 Accepted`:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "REQUEUED"
}
```

---

## Health & Metrics

### Health Check

Liveness probe.

```
GET /health
```

**Authentication**: Not required

**Response** `200 OK`:
```json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Readiness Check

Readiness probe with dependency checks.

```
GET /ready
```

**Authentication**: Not required

**Response** `200 OK`:
```json
{
  "status": "ready",
  "dependencies": {
    "redis": "ok",
    "postgres": "ok"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Response** `503 Service Unavailable`:
```json
{
  "status": "not_ready",
  "dependencies": {
    "redis": "ok",
    "postgres": "error: connection refused"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Metrics

Prometheus metrics endpoint.

```
GET /metrics
```

**Authentication**: Not required

**Response**: Prometheus text format

---

## WebSocket

### Connect

```
ws://localhost:8000/ws/decisions?api_key=your-key
```

Or with header:
```
X-API-Key: your-key
```

### Messages

**Subscribe**:
```json
{
  "action": "subscribe",
  "filters": {
    "model": "chatgpt",
    "symbol": "BTC",
    "event_type": "OPEN_SIGNAL"
  }
}
```

**Unsubscribe**:
```json
{
  "action": "unsubscribe"
}
```

**Decision (server → client)**:
```json
{
  "type": "decision",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTC",
  "event_type": "OPEN_SIGNAL",
  "model": "chatgpt",
  "decision": {
    "decision": "FOLLOW_ENTER",
    "confidence": 0.78,
    "entry_plan": { "type": "limit", "offset_bps": -5 },
    "risk_plan": { "stop_method": "atr", "atr_multiple": 2.0 },
    "size_pct": 15,
    "reasons": ["bullish_ema_alignment"]
  },
  "published_at": "2024-01-15T10:30:04.510Z"
}
```

**Error (server → client)**:
```json
{
  "type": "error",
  "code": "INVALID_FILTER",
  "message": "Unknown model: invalid_model"
}
```

**Heartbeat**:
```json
{ "type": "ping" }
{ "type": "pong" }
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request body or parameters |
| `UNAUTHORIZED` | 401 | Invalid or missing API key |
| `FORBIDDEN` | 403 | Insufficient permissions |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMITED` | 429 | Rate limit exceeded |
| `INTERNAL_ERROR` | 500 | Internal server error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |
