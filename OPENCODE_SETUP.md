# Conectar Hubia (Qwen Proxy) con OpenCode

Esta guía te muestra cómo integrar el proxy Qwen con OpenCode para usar modelos de Qwen directamente desde tu entorno de desarrollo.

## Requisitos

- [Bun](https://bun.sh) v1.0+ instalado
- [OpenCode](https://opencode.ai) instalado
- Cuenta en [chat.qwen.ai](https://chat.qwen.ai)

## Instalación Rápida

### Opción 1: Script Automático (Recomendado)

```bash
# Desde el directorio del proyecto hubia
./setup-opencode.sh
```

Este script automáticamente:
- Verifica que el proxy esté corriendo
- Agrega el provider `qwen` a tu configuración de OpenCode
- Configura los modelos disponibles
- Te da instrucciones para usarlo

### Opción 2: Instalación Manual

#### 1. Inicia el Proxy Qwen

```bash
# En el directorio del proyecto hubia
bun install
bun run start
```

El servidor iniciará en `http://localhost:8089`

#### 2. Obtén tu JWT Token de Qwen

1. Ve a [chat.qwen.ai](https://chat.qwen.ai) e inicia sesión
2. Abre DevTools (F12) → Application → Local Storage
3. Busca la clave `token` y copia su valor

#### 3. Configura el Token en el Proxy

```bash
curl -X POST http://localhost:8089/v1/auth/qwen \
  -H "Content-Type: application/json" \
  -d '{
    "token": "TU_JWT_TOKEN_AQUI"
  }'
```

O usa el dashboard web en `http://localhost:8089/`

#### 4. Configura OpenCode

Agrega el provider `qwen` a tu `~/.config/opencode/opencode.json`:

```json
{
  "provider": {
    "qwen": {
      "api": "openai",
      "name": "Qwen Proxy",
      "options": {
        "baseURL": "http://localhost:8089/v1",
        "apiKey": "not-needed"
      },
      "models": {
        "qwen3.7-max": {
          "name": "Qwen3.7-Max",
          "limit": {
            "context": 1000000,
            "output": 65536
          }
        },
        "qwen3.6-plus": {
          "name": "Qwen3.6-Plus",
          "limit": {
            "context": 1000000,
            "output": 65536
          }
        }
      }
    }
  }
}
```

#### 5. Reinicia OpenCode

OpenCode no recarga la configuración en caliente, así que necesitas reiniciarlo:

```bash
# Si OpenCode está corriendo, ciérralo y vuelve a iniciarlo
opencode
```

## Uso

### Usar Qwen como Modelo por Defecto

Agrega a tu `opencode.json`:

```json
{
  "model": "qwen/qwen3.7-max"
}
```

### Usar Qwen desde la Línea de Comandos

```bash
opencode --model qwen/qwen3.7-max
```

### Usar Qwen en un Agente Específico

```json
{
  "agent": {
    "build": {
      "model": "qwen/qwen3.7-max"
    }
  }
}
```

## Modelos Disponibles

El proxy expone dinámicamente todos los modelos disponibles en tu cuenta de Qwen. Para ver la lista completa:

```bash
curl http://localhost:8089/v1/models | jq '.data[].id'
```

Modelos principales:
- `qwen/qwen3.7-max` — El más potente (1M contexto)
- `qwen/qwen3.6-plus` — Balance velocidad/potencia (1M contexto)
- `qwen/qwen3.6-max-preview` — Preview del próximo flagship (262K contexto)
- `qwen/qwen3.6-27b` — Modelo denso optimizado (262K contexto)
- `qwen/qwen3.5-plus` — Versión anterior estable (1M contexto)

## Configuración Avanzada

### Configurar Múltiples Modelos

Puedes agregar todos los modelos que quieras en la configuración:

```json
{
  "provider": {
    "qwen": {
      "api": "openai",
      "name": "Qwen Proxy",
      "options": {
        "baseURL": "http://localhost:8089/v1",
        "apiKey": "not-needed"
      },
      "models": {
        "qwen3.7-max": {
          "name": "Qwen3.7-Max",
          "limit": { "context": 1000000, "output": 65536 }
        },
        "qwen3.6-plus": {
          "name": "Qwen3.6-Plus",
          "limit": { "context": 1000000, "output": 65536 }
        },
        "qwen3.6-27b": {
          "name": "Qwen3.6-27B",
          "limit": { "context": 262144, "output": 65536 }
        }
      }
    }
  }
}
```

### Usar Diferentes Modelos para Diferentes Agentes

```json
{
  "model": "qwen/qwen3.7-max",
  "small_model": "qwen/qwen3.6-plus",
  "agent": {
    "build": {
      "model": "qwen/qwen3.7-max"
    },
    "explore": {
      "model": "qwen/qwen3.6-plus"
    }
  }
}
```

### Configurar Timeouts

Si experimentas timeouts con modelos lentos:

```json
{
  "provider": {
    "qwen": {
      "api": "openai",
      "options": {
        "baseURL": "http://localhost:8089/v1",
        "apiKey": "not-needed",
        "timeout": 300000
      }
    }
  }
}
```

## Solución de Problemas

### "Provider qwen not found"

- Verifica que el provider esté en `~/.config/opencode/opencode.json`
- Reinicia OpenCode después de hacer cambios en la configuración

### "Connection refused" o "ECONNREFUSED"

- Verifica que el proxy esté corriendo: `curl http://localhost:8089/health`
- Inicia el proxy: `bun run start`

### "Qwen credentials not configured"

- Configura tu JWT token: `curl -X POST http://localhost:8089/v1/auth/qwen -H "Content-Type: application/json" -d '{"token":"TU_TOKEN"}'`
- O usa el dashboard web en `http://localhost:8089/`

### "Invalid or expired JWT token"

- Tu token JWT de Qwen expiró (dura ~30 días)
- Ve a [chat.qwen.ai](https://chat.qwen.ai), inicia sesión nuevamente
- Extrae el nuevo token y configúralo en el proxy

### El modelo no responde o tarda mucho

- Verifica que el proxy tenga `idleTimeout: 120` en `src/index.ts`
- Los modelos más grandes (qwen3.7-max) pueden tardar más en responder
- Considera usar un modelo más rápido como `qwen3.6-plus`

## Arquitectura

```
┌─────────────┐
│  OpenCode   │
└──────┬──────┘
       │
       │ HTTP (OpenAI-compatible API)
       │
       ▼
┌─────────────────┐
│  Hubia Proxy    │  http://localhost:8089
│  (Bun + Hono)   │
└──────┬──────────┘
       │
       │ HTTPS (Bearer JWT)
       │
       ▼
┌─────────────────┐
│  Qwen API       │  https://chat.qwen.ai
│  (chat.qwen.ai) │
└─────────────────┘
```

## Comandos Útiles

```bash
# Iniciar proxy en modo desarrollo (auto-reload)
bun run dev

# Iniciar proxy en modo producción
bun run start

# Verificar que el proxy esté corriendo
curl http://localhost:8089/health

# Listar modelos disponibles
curl http://localhost:8089/v1/models | jq '.data[].id'

# Configurar token JWT de Qwen
curl -X POST http://localhost:8089/v1/auth/qwen \
  -H "Content-Type: application/json" \
  -d '{"token":"TU_JWT_TOKEN"}'

# Probar chat completion
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Abrir dashboard web
open http://localhost:8089/
```

## Soporte

Si encuentras problemas:

1. Verifica los logs del proxy: `tail -f /tmp/hubia.log`
2. Abre el dashboard web para debugging: `http://localhost:8089/`
3. Revisa la [documentación de OpenCode](https://opencode.ai/docs)
4. Reporta issues en el repositorio del proyecto

## Licencia

MIT
