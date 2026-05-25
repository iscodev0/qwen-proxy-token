#!/usr/bin/env bash
set -e

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Hubia - Qwen Proxy → OpenCode Integration Setup         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Verificar que Bun esté instalado
if ! command -v bun &> /dev/null; then
    echo -e "${RED}✗ Bun no está instalado${NC}"
    echo "  Instala Bun desde: https://bun.sh"
    exit 1
fi
echo -e "${GREEN}✓ Bun instalado${NC}"

# Verificar que OpenCode esté instalado
if ! command -v opencode &> /dev/null; then
    echo -e "${YELLOW}⚠ OpenCode no está instalado${NC}"
    echo "  Instala OpenCode desde: https://opencode.ai"
    echo "  Puedes continuar con la configuración manual más tarde"
    echo ""
fi

# Verificar que el proxy esté corriendo
echo -e "${BLUE}Verificando proxy Qwen...${NC}"
if curl -s http://localhost:8089/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Proxy corriendo en http://localhost:8089${NC}"
else
    echo -e "${YELLOW}⚠ Proxy no está corriendo${NC}"
    echo ""
    read -p "¿Quieres iniciar el proxy ahora? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${BLUE}Iniciando proxy...${NC}"
        bun install > /dev/null 2>&1
        bun run start > /tmp/hubia.log 2>&1 &
        PROXY_PID=$!
        sleep 3
        
        if curl -s http://localhost:8089/health > /dev/null 2>&1; then
            echo -e "${GREEN}✓ Proxy iniciado (PID: $PROXY_PID)${NC}"
        else
            echo -e "${RED}✗ Error al iniciar el proxy${NC}"
            echo "  Revisa los logs: tail -f /tmp/hubia.log"
            exit 1
        fi
    else
        echo -e "${YELLOW}Continuando sin el proxy...${NC}"
        echo "  Recuerda iniciarlo después con: bun run start"
    fi
fi

# Verificar si hay un token JWT configurado
echo ""
echo -e "${BLUE}Verificando configuración de Qwen JWT...${NC}"
RESPONSE=$(curl -s http://localhost:8089/v1/models 2>&1)
if echo "$RESPONSE" | grep -q "Qwen credentials not configured"; then
    echo -e "${YELLOW}⚠ Token JWT de Qwen no configurado${NC}"
    echo ""
    echo "Para obtener tu token JWT:"
    echo "  1. Ve a https://chat.qwen.ai e inicia sesión"
    echo "  2. Abre DevTools (F12) → Application → Local Storage"
    echo "  3. Copia el valor de la clave 'token'"
    echo ""
    read -p "¿Quieres configurar el token ahora? (y/n): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Pega tu JWT token: " JWT_TOKEN
        if [ -n "$JWT_TOKEN" ]; then
            RESULT=$(curl -s -X POST http://localhost:8089/v1/auth/qwen \
                -H "Content-Type: application/json" \
                -d "{\"token\":\"$JWT_TOKEN\"}")
            
            if echo "$RESULT" | grep -q "success"; then
                echo -e "${GREEN}✓ Token JWT configurado${NC}"
            else
                echo -e "${RED}✗ Error al configurar el token${NC}"
                echo "  Respuesta: $RESULT"
            fi
        fi
    fi
else
    echo -e "${GREEN}✓ Token JWT configurado${NC}"
fi

# Configurar OpenCode
echo ""
echo -e "${BLUE}Configurando OpenCode...${NC}"

OPENCODE_CONFIG="$HOME/.config/opencode/opencode.json"

# Crear directorio si no existe
mkdir -p "$(dirname "$OPENCODE_CONFIG")"

# Verificar si el archivo existe
if [ ! -f "$OPENCODE_CONFIG" ]; then
    echo -e "${YELLOW}⚠ Archivo de configuración de OpenCode no encontrado${NC}"
    echo "  Creando: $OPENCODE_CONFIG"
    echo '{"$schema":"https://opencode.ai/config.json"}' > "$OPENCODE_CONFIG"
fi

# Backup del archivo original
cp "$OPENCODE_CONFIG" "$OPENCODE_CONFIG.backup.$(date +%Y%m%d_%H%M%S)"
echo -e "${GREEN}✓ Backup creado${NC}"

# Crear script temporal para actualizar JSON
cat > /tmp/update-opencode-config.ts << 'EOF'
import { readFileSync, writeFileSync } from 'fs';
import { parse } from 'jsonc-parser';

const configPath = process.argv[2];
const content = readFileSync(configPath, 'utf8');
const config = parse(content);

// Add qwen provider
config.provider = config.provider || {};
config.provider.qwen = {
  api: 'openai',
  name: 'Qwen Proxy',
  options: {
    baseURL: 'http://localhost:8089/v1',
    apiKey: 'not-needed'
  },
  models: {
    'qwen3.7-max': {
      name: 'Qwen3.7-Max',
      limit: { context: 1000000, output: 65536 }
    },
    'qwen3.6-plus': {
      name: 'Qwen3.6-Plus',
      limit: { context: 1000000, output: 65536 }
    },
    'qwen3.6-max-preview': {
      name: 'Qwen3.6-Max-Preview',
      limit: { context: 262144, output: 65536 }
    }
  }
};

writeFileSync(configPath, JSON.stringify(config, null, 2));
console.log('Config updated successfully');
EOF

# Instalar jsonc-parser si no está disponible
if ! bun pm ls 2>/dev/null | grep -q jsonc-parser; then
    echo -e "${BLUE}Instalando jsonc-parser...${NC}"
    bun add jsonc-parser > /dev/null 2>&1
fi

# Actualizar configuración
echo -e "${BLUE}Actualizando configuración de OpenCode...${NC}"
if bun run /tmp/update-opencode-config.ts "$OPENCODE_CONFIG" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Provider 'qwen' agregado a OpenCode${NC}"
else
    echo -e "${RED}✗ Error al actualizar configuración${NC}"
    echo "  Puedes configurarlo manualmente. Ver: OPENCODE_SETUP.md"
    exit 1
fi

# Preguntar si quiere configurar como modelo por defecto
echo ""
read -p "¿Quieres configurar qwen/qwen3.7-max como modelo por defecto? (y/n): " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cat > /tmp/set-default-model.ts << 'EOF'
import { readFileSync, writeFileSync } from 'fs';
import { parse } from 'jsonc-parser';

const configPath = process.argv[2];
const content = readFileSync(configPath, 'utf8');
const config = parse(content);

config.model = 'qwen/qwen3.7-max';
config.small_model = 'qwen/qwen3.6-plus';

writeFileSync(configPath, JSON.stringify(config, null, 2));
console.log('Default model set');
EOF
    
    bun run /tmp/set-default-model.ts "$OPENCODE_CONFIG" > /dev/null 2>&1
    echo -e "${GREEN}✓ Modelo por defecto configurado: qwen/qwen3.7-max${NC}"
fi

# Limpiar archivos temporales
rm -f /tmp/update-opencode-config.ts /tmp/set-default-model.ts

# Resumen final
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    ¡Configuración Completa!                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}✓ Proxy Qwen:${NC} http://localhost:8089"
echo -e "${GREEN}✓ Dashboard:${NC}  http://localhost:8089/"
echo -e "${GREEN}✓ Provider:${NC}   qwen (agregado a OpenCode)"
echo ""
echo -e "${YELLOW}Próximos pasos:${NC}"
echo ""
echo "  1. Reinicia OpenCode para cargar la nueva configuración:"
echo "     ${BLUE}opencode${NC}"
echo ""
echo "  2. Usa modelos de Qwen:"
echo "     ${BLUE}opencode --model qwen/qwen3.7-max${NC}"
echo ""
echo "  3. O configura en opencode.json:"
echo "     ${BLUE}\"model\": \"qwen/qwen3.7-max\"${NC}"
echo ""
echo -e "${BLUE}Modelos disponibles:${NC}"
echo "  • qwen/qwen3.7-max       (1M contexto, más potente)"
echo "  • qwen/qwen3.6-plus      (1M contexto, balance)"
echo "  • qwen/qwen3.6-max-preview (262K contexto, preview)"
echo ""
echo -e "${YELLOW}Para más información:${NC}"
echo "  • Guía completa: ${BLUE}OPENCODE_SETUP.md${NC}"
echo "  • Dashboard web: ${BLUE}http://localhost:8089/${NC}"
echo "  • Documentación: ${BLUE}https://opencode.ai/docs${NC}"
echo ""
