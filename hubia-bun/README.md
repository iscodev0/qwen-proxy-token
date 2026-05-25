# Hubia Bun - Qwen Proxy

OpenAI-compatible API proxy for Qwen AI built with **Bun** and **Hono** for maximum performance.

## Features

- **OpenAI-compatible API** — Drop-in replacement for OpenAI SDK
- **Streaming support** — Real-time Server-Sent Events (SSE)
- **Bearer JWT auth** — Direct email/password authentication to Qwen
- **Dynamic models** — Automatically fetches available models from Qwen API
- **Auto token refresh** — JWT tokens are cached and refreshed automatically
- **High performance** — Built with Bun runtime for speed

## Quick Start

### Prerequisites

- [Bun](https://bun.sh) v1.0+

### Installation

```bash
cd hubia-bun
bun install
```

### Configuration

Copy `.env.example` to `.env` and configure:

```bash
cp .env.example .env
```

Edit `.env`:
```
PORT=8089
HOST=0.0.0.0
SECRET_KEY=your-secret-key-here
```

### Start the Server

```bash
# Development mode (with auto-reload)
bun run dev

# Production mode
bun run start
```

The server will start on `http://localhost:8089` by default.

## API Usage

### 1. Login to get JWT token

```bash
curl -X POST http://localhost:8089/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "myuser",
    "password": "mypassword"
  }'
```

Response:
```json
{
  "token": "eyJhbGc...",
  "user": { "id": 1, "username": "myuser" }
}
```

### 2. Configure Qwen JWT Token

Get your JWT token from chat.qwen.ai:
1. Login at [chat.qwen.ai](https://chat.qwen.ai)
2. Open DevTools (F12) → Application → Local Storage
3. Copy the `token` value

```bash
curl -X POST http://localhost:8089/v1/auth/qwen \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

### 3. List available models

```bash
curl http://localhost:8089/v1/models \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### 4. Chat completion (non-streaming)

```bash
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### 5. Chat completion (streaming)

```bash
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "stream": true
  }'
```

## Using with OpenAI SDK

```typescript
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8089/v1",
  apiKey: "YOUR_JWT_TOKEN",
});

const response = await client.chat.completions.create({
  model: "qwen/qwen3.7-max",
  messages: [
    { role: "user", content: "Hello!" }
  ],
});

console.log(response.choices[0].message.content);
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/auth/login` | Login to get proxy JWT token |
| POST | `/v1/auth/qwen` | Configure Qwen JWT token |
| GET | `/v1/models` | List available models |
| POST | `/v1/chat/completions` | Chat completion (stream or non-stream) |
| GET | `/health` | Health check |
| GET | `/` | Dashboard & API info |

## Architecture

```
hubia-bun/
├── src/
│   ├── index.ts          # Entry point
│   ├── auth.ts           # JWT auth middleware
│   ├── types.ts          # TypeScript types
│   ├── db/
│   │   └── index.ts      # SQLite database
│   ├── providers/
│   │   └── qwen.ts       # Qwen API provider
│   └── routes/
│       └── v1.ts         # API routes
├── package.json
└── tsconfig.json
```

## Performance

Built with Bun + Hono for maximum performance:
- **Bun runtime** — 3x faster than Node.js
- **Hono framework** — Ultra-fast, lightweight web framework
- **Native SQLite** — better-sqlite3 for fast database access
- **Streaming SSE** — Real-time response streaming

## Migration from Python

This is a complete rewrite of the original Python/FastAPI version with:
- Removed web scraping system (Scrapling, Playwright)
- Direct Bearer JWT authentication
- Simplified architecture
- Better performance with Bun runtime

## License

MIT
