# Qwen Proxy

OpenAI-compatible API proxy for [Qwen AI](https://chat.qwen.ai/). Access Qwen models through a familiar API interface, with support for streaming and non-streaming completions.

## Features

- **OpenAI-compatible API** — Drop-in replacement for OpenAI SDK and tools
- **Streaming support** — Real-time Server-Sent Events (SSE) streaming
- **System prompts** — Full support for OpenAI-compatible system messages
- **Thinking mode** — Enable reasoning and step-by-step thinking
- **Web search** — Built-in web search tool for current information
- **Code interpreter** — Execute Python code directly in conversations
- **Auto chat creation** — Each request creates a fresh chat (no context pollution)
- **Web UI** — Browser-based interface for credential management and API testing
- **Auto-capture** — Interactive browser-based cookie capture
- **CLI** — Simple command-line interface to start/stop the server

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd hubia

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install the package
pip install -e .
```

### Start the Server

```bash
# Using the CLI
qwen-proxy start

# Or directly with uvicorn
uvicorn hubia.main:app --host 0.0.0.0 --port 8089
```

### Set Up Qwen Credentials

1. Open your browser to `http://localhost:8089/`
2. Go to the **Credentials** tab
3. Either use **Auto-Capture** (recommended) or manually enter your Qwen token:
   - Log in to [chat.qwen.ai](https://chat.qwen.ai/)
   - Open DevTools (F12) → Application → Local Storage
   - Copy the `token` value
4. Save your credentials

### Use the API

```bash
# List available models
curl http://localhost:8089/v1/models

# Chat completion
curl http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Streaming chat completion
curl http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": true
  }'
```

## System Prompts

The provider fully supports OpenAI-compatible system prompts. If the first message in your request has `role: "system"`, it will be used as the system prompt for the conversation.

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "system", "content": "You are a pirate. Always respond in pirate speak."},
      {"role": "user", "content": "Say hello"}
    ]
  }'
```

**Python example:**

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",
)

response = client.chat.completions.create(
    model="qwen/qwen3.7-max",
    messages=[
        {"role": "system", "content": "You are a helpful assistant specialized in Python."},
        {"role": "user", "content": "Explain list comprehensions"},
    ],
)
print(response.choices[0].message.content)
```

## Tools and Features

Configure advanced features via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `QWEN_CHAT_MODE` | `normal` | Chat mode: `normal`, `thinking`, `search`, `code` |
| `QWEN_ENABLE_THINKING` | `true` | Enable thinking/reasoning mode |
| `QWEN_ENABLE_SEARCH` | `false` | Enable web search tool |
| `QWEN_ENABLE_CODE_INTERPRETER` | `false` | Enable code interpreter tool |
| `QWEN_CHAT_ID` | (auto) | Reuse existing chat (optional) |

### Thinking Mode

Enable step-by-step reasoning for complex problems:

```bash
export QWEN_ENABLE_THINKING="true"
export QWEN_CHAT_MODE="thinking"

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "user", "content": "What is 15 * 23? Show your reasoning."}
    ]
  }'
```

### Web Search

Enable web search for current information:

```bash
export QWEN_ENABLE_SEARCH="true"
export QWEN_CHAT_MODE="search"

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "user", "content": "What is the current weather in Buenos Aires?"}
    ]
  }'
```

### Code Interpreter

Enable Python code execution:

```bash
export QWEN_ENABLE_CODE_INTERPRETER="true"
export QWEN_CHAT_MODE="code"

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "user", "content": "Write a Python function to calculate fibonacci numbers and test it with n=10"}
    ]
  }'
```

### Combined Features

You can combine system prompts with tools:

```bash
export QWEN_ENABLE_THINKING="true"
export QWEN_CHAT_MODE="thinking"

curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "system", "content": "You are a math tutor. Explain concepts step by step."},
      {"role": "user", "content": "Explain why the square root of 2 is irrational"}
    ]
  }'
```

## Testing

Run the comprehensive test suite to verify all features:

```bash
python test_qwen_features.py
```

This script tests:
1. Basic chat completion
2. System prompt support
3. Thinking/reasoning mode
4. Web search tool
5. Code interpreter tool
6. Combined features

## Chat Management

The provider automatically creates a new chat for each request to avoid context pollution. If you want to reuse an existing chat (e.g., for conversation continuity):

```bash
# Get your chat ID
python get_chat_id.py

# Set it in environment
export QWEN_CHAT_ID="your-chat-id-here"
```



```bash
# Start the server
qwen-proxy start [--host HOST] [--port PORT] [--reload]

# Check server status
qwen-proxy status

# Show version
qwen-proxy version
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/models` | List available models |
| POST | `/v1/chat/completions` | Chat completion (streaming or non-streaming) |
| GET | `/health` | Health check |
| GET | `/docs` | OpenAPI documentation |
| GET | `/` | Web UI |

## Python Usage

```python
import httpx

BASE_URL = "http://localhost:8000"

# List models
resp = httpx.get(f"{BASE_URL}/v1/models")
print(resp.json())

# Chat completion
resp = httpx.post(f"{BASE_URL}/v1/chat/completions",
    json={
        "model": "qwen/qwen3.7-max",
        "messages": [{"role": "user", "content": "Hello!"}],
    })
print(resp.json())

# Streaming
with httpx.stream("POST", f"{BASE_URL}/v1/chat/completions",
    json={
        "model": "qwen/qwen3.7-max",
        "messages": [{"role": "user", "content": "Hello!"}],
        "stream": True,
    }) as resp:
    for line in resp.iter_lines():
        if line.startswith("data: "):
            print(line[6:])
```

## Using with OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed",  # No API key required
)

response = client.chat.completions.create(
    model="qwen/qwen3.7-max",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

## How to Get Qwen Credentials

### Method 1: Auto-Capture (Recommended)

1. Start the server and open the Web UI
2. Go to **Credentials** tab
3. Click **Capture Qwen Token**
4. A browser window opens — log in to Qwen
5. Click **Done — Extract Token** in the Web UI
6. Cookies are captured automatically

### Method 2: Manual Token

1. Open [chat.qwen.ai](https://chat.qwen.ai/) in your browser
2. Log in to your account
3. Press F12 to open DevTools
4. Go to **Application** → **Local Storage** → `https://chat.qwen.ai`
5. Find the `token` key and copy its value
6. Paste it in the Web UI and save

## Configuration

Configuration is managed via environment variables or a `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `0.0.0.0` | Server bind host |
| `PORT` | `8081` | Server bind port |
| `DATABASE_URL` | `sqlite+aiosqlite:///./hubia.db` | Database connection string |
| `SECRET_KEY` | `change-me` | JWT signing key |
| `CORS_ORIGINS` | (see config.py) | Allowed CORS origins |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Start with auto-reload
qwen-proxy start --reload
```

## License

MIT
