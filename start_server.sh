#!/bin/bash
# Script to start Qwen Proxy server and keep it running

cd /home/iscodev/Documents/project/iscodev/hubia

echo "Starting Qwen Proxy server..."
echo "Logs will be written to /tmp/qwen-proxy.log"
echo "Press Ctrl+C to stop the server"
echo ""

# Start server in foreground so we can see the output
.venv/bin/uvicorn hubia.main:app --host 0.0.0.0 --port 8089 2>&1 | tee /tmp/qwen-proxy.log
