# Hubia - Qwen Proxy

OpenAI-compatible API proxy for Qwen AI built with **Bun** and **Hono** for maximum performance.

## Features

- **OpenAI-compatible API** — Drop-in replacement for OpenAI SDK
- **Streaming support** — Real-time Server-Sent Events (SSE)
- **Bearer JWT auth** — Direct JWT token authentication to Qwen
- **Dynamic models** — Automatically fetches 23+ available models from Qwen API
- **Auto token refresh** — JWT tokens are cached and validated automatically
- **High performance** — Built with Bun runtime for speed
- **Web Dashboard** — Interactive UI for configuration and testing

## Quick Start

### Prerequisites

- [Bun](https://bun.sh) v1.0+

### Installation

```bash
bun install
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

### 1. Configure Qwen JWT Token

Get your JWT token from chat.qwen.ai:
1. Login at [chat.qwen.ai](https://chat.qwen.ai)
2. Open DevTools (F12) → Application → Local Storage
3. Copy the `token` value

```bash
curl -X POST http://localhost:8089/v1/auth/qwen \
  -H "Content-Type: application/json" \
  -d '{
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

### 2. List available models

```bash
curl http://localhost:8089/v1/models
```

### 3. Chat completion (non-streaming)

```bash
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ]
  }'
```

### 4. Chat completion (streaming)

```bash
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
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
  apiKey: "not-needed",
});

const response = await client.chat.completions.create({
  model: "qwen/qwen3.7-max",
  messages: [
    { role: "user", content: "Hello!" }
  ],
});

console.log(response.choices[0].message.content);
```

## Web Dashboard

Open `http://localhost:8089/` in your browser to access the interactive dashboard:

- **Dashboard** — Overview and quick start guide
- **Qwen Token** — Configure your Qwen JWT token
- **Models** — Browse all available models
- **Playground** — Test chat completions with streaming support

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/auth/qwen` | Configure Qwen JWT token |
| GET | `/v1/models` | List available models |
| POST | `/v1/chat/completions` | Chat completion (stream or non-stream) |
| GET | `/health` | Health check |
| GET | `/` | Dashboard & API info |

## Architecture

```
hubia/
├── src/
│   ├── index.ts          # Entry point
│   ├── types.ts          # TypeScript types
│   ├── db/
│   │   └── index.ts      # SQLite database
│   ├── providers/
│   │   └── qwen.ts       # Qwen API provider
│   └── routes/
│       └── v1.ts         # API routes
├── public/
│   └── index.html        # Web dashboard
├── package.json
└── tsconfig.json
```

## Performance

Built with Bun + Hono for maximum performance:
- **Bun runtime** — 3x faster than Node.js
- **Hono framework** — Ultra-fast, lightweight web framework
- **Native SQLite** — bun:sqlite for fast database access
- **Streaming SSE** — Real-time response streaming with 120s timeout

## License

MIT
