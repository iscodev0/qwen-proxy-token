# Qwen Proxy - Guía de Uso

## 🚀 Inicio Rápido

### 1. Iniciar el Servidor

```bash
cd /home/iscodev/Documents/project/iscodev/hubia

# Opción 1: Usando el CLI (recomendado)
.venv/bin/qwen-proxy start

# Opción 2: Con auto-reload para desarrollo
.venv/bin/qwen-proxy start --reload

# Opción 3: Usando uvicorn directamente
.venv/bin/uvicorn hubia.main:app --host 0.0.0.0 --port 8089 --reload
```

El servidor iniciará en `http://localhost:8089`

### 2. Verificar que Funciona

```bash
# Health check
curl http://localhost:8089/health

# Listar modelos disponibles
curl http://localhost:8089/v1/models
```

### 3. Configurar Credenciales de Qwen

1. Abre `http://localhost:8089/` en tu navegador
2. Ve a la sección de credenciales
3. Captura las cookies de Qwen:
   - Abre https://chat.qwen.ai/ en otra pestaña
   - Inicia sesión
   - Abre DevTools (F12) → Application → Cookies
   - Copia todas las cookies como JSON
   - Pégalas en el formulario del proxy

## 📚 Modelos Disponibles

| Modelo | ID | Descripción |
|--------|-----|-------------|
| Qwen 3.7 Max | `qwen/qwen3.7-max` | Modelo flagship con razonamiento avanzado |
| Qwen 3.6 Plus | `qwen/qwen3.6-plus` | Modelo multimodal (texto, imagen, video, audio) |
| Qwen 3.6 Max Preview | `qwen/qwen3.6-max-preview` | Versión preview con contexto extendido (262K tokens) |

## 🎛️ Configuración de Features

### Variables de Entorno

Puedes configurar las características del provider usando variables de entorno:

```bash
# Modo de chat (normal, thinking, search, code)
export QWEN_CHAT_MODE="normal"

# Habilitar/deshabilitar thinking mode
export QWEN_ENABLE_THINKING="true"

# Habilitar/deshabilitar búsqueda web
export QWEN_ENABLE_SEARCH="false"

# Habilitar/deshabilitar intérprete de código
export QWEN_ENABLE_CODE_INTERPRETER="false"

# Reutilizar un chat específico (opcional)
export QWEN_CHAT_ID="your-chat-id-here"
```

### Ejemplos de Uso

#### 1. Chat Normal (por defecto)

```bash
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.6-plus",
    "messages": [
      {"role": "user", "content": "Hola, ¿cómo estás?"}
    ],
    "stream": false
  }'
```

#### 2. Con System Prompt

```bash
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "system", "content": "Eres un experto en Python. Responde siempre con ejemplos de código."},
      {"role": "user", "content": "¿Cómo leo un archivo JSON?"}
    ],
    "stream": false
  }'
```

#### 3. Con Thinking Mode Habilitado

```bash
# Iniciar servidor con thinking habilitado
QWEN_ENABLE_THINKING=true QWEN_CHAT_MODE=thinking .venv/bin/qwen-proxy start

# Hacer request
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.7-max",
    "messages": [
      {"role": "user", "content": "Resuelve: Si un tren viaja a 120 km/h, ¿cuánto tarda en recorrer 450 km?"}
    ],
    "stream": false
  }'
```

#### 4. Con Búsqueda Web Habilitada

```bash
# Iniciar servidor con search habilitado
QWEN_ENABLE_SEARCH=true QWEN_CHAT_MODE=search .venv/bin/qwen-proxy start

# Hacer request
curl -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.6-plus",
    "messages": [
      {"role": "user", "content": "¿Cuáles son las últimas noticias sobre IA en 2026?"}
    ],
    "stream": false
  }'
```

#### 5. Streaming (SSE)

```bash
curl -N -X POST http://localhost:8089/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.6-plus",
    "messages": [
      {"role": "user", "content": "Cuenta del 1 al 10"}
    ],
    "stream": true
  }'
```

## 🔌 Integración con OpenCode

### Configuración en opencode.json

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "qwen-proxy": {
      "api": "openai",
      "name": "Qwen Proxy",
      "options": {
        "baseURL": "http://localhost:8089/v1",
        "apiKey": "not-needed"
      },
      "models": {
        "qwen/qwen3.7-max": {
          "id": "qwen/qwen3.7-max",
          "name": "Qwen 3.7 Max",
          "family": "qwen",
          "reasoning": true,
          "temperature": true,
          "tool_call": true,
          "limit": {
            "context": 131072,
            "output": 8192
          },
          "modalities": {
            "input": ["text"],
            "output": ["text"]
          },
          "cost": {
            "input": 0,
            "output": 0
          }
        },
        "qwen/qwen3.6-plus": {
          "id": "qwen/qwen3.6-plus",
          "name": "Qwen 3.6 Plus",
          "family": "qwen",
          "reasoning": true,
          "temperature": true,
          "tool_call": true,
          "limit": {
            "context": 131072,
            "output": 8192
          },
          "modalities": {
            "input": ["text", "image", "video", "audio"],
            "output": ["text"]
          },
          "cost": {
            "input": 0,
            "output": 0
          }
        }
      }
    }
  },
  "model": "qwen-proxy/qwen/qwen3.7-max",
  "small_model": "qwen-proxy/qwen/qwen3.6-plus"
}
```

### Uso con OpenCode

```bash
# Iniciar el proxy
.venv/bin/qwen-proxy start

# En otra terminal, iniciar OpenCode
opencode
```

OpenCode usará automáticamente `qwen/qwen3.7-max` como modelo principal y `qwen/qwen3.6-plus` para tareas pequeñas.

## 🐛 Solución de Problemas

### Error: "Model not found"

**Causa**: El ID del modelo no coincide con los disponibles en la API.

**Solución**: Verifica los modelos disponibles:
```bash
curl http://localhost:8089/v1/models
```

Usa el ID exacto que devuelve la API (ej: `qwen/qwen3.7-max`).

### Error: "No chats found"

**Causa**: No hay chats creados en tu cuenta de Qwen.

**Solución**: 
1. Ve a https://chat.qwen.ai/
2. Crea un nuevo chat enviando cualquier mensaje
3. El proxy usará ese chat automáticamente

### Error: "Session expired"

**Causa**: Las cookies de Qwen han expirado.

**Solución**: 
1. Ve a https://chat.qwen.ai/ e inicia sesión nuevamente
2. Captura las nuevas cookies
3. Actualízalas en el proxy

### Respuesta vacía

**Causa**: El parsing de SSE no está funcionando correctamente.

**Solución**: Reinicia el servidor:
```bash
pkill -f "qwen-proxy"
.venv/bin/qwen-proxy start
```

## 📝 Scripts de Prueba

### Probar Features con Variables de Entorno

```bash
# Probar con thinking habilitado
.venv/bin/python test_env_features.py

# Probar con search habilitado
QWEN_ENABLE_SEARCH=true QWEN_CHAT_MODE=search .venv/bin/python test_env_features.py

# Probar con thinking deshabilitado
QWEN_ENABLE_THINKING=false .venv/bin/python test_env_features.py
```

### Obtener Chat ID

```bash
# Script para obtener el ID de un chat existente
.venv/bin/python get_chat_id.py
```

## 🔧 Comandos Útiles

```bash
# Verificar estado del servidor
.venv/bin/qwen-proxy status

# Ver versión
.venv/bin/qwen-proxy version

# Detener servidor
pkill -f "qwen-proxy"

# Ver logs del servidor (si está corriendo en background)
tail -f /tmp/qwen-proxy.log
```

## 📚 Recursos Adicionales

- **Documentación de OpenCode**: https://opencode.ai/docs
- **Qwen AI**: https://chat.qwen.ai/
- **API OpenAI Compatible**: https://platform.openai.com/docs/api-reference

## 💡 Consejos

1. **Usa streaming** para respuestas más rápidas y mejor UX
2. **System prompts** son muy útiles para personalizar el comportamiento
3. **Thinking mode** mejora las respuestas en problemas complejos
4. **Search mode** es ideal para preguntas sobre eventos actuales
5. **Reutiliza chats** con `QWEN_CHAT_ID` para mantener contexto

## 🆘 Soporte

Si encuentras problemas:
1. Verifica que el servidor esté corriendo: `curl http://localhost:8089/health`
2. Revisa los logs del servidor
3. Verifica que las cookies de Qwen sean válidas
4. Asegúrate de usar los IDs de modelo correctos
