#!/usr/bin/env bash
set -euo pipefail

echo "===================================================================="
echo " S&P 100 NLP Risk Engine - Docker Compose Launcher"
echo "===================================================================="
echo ""

echo "[*] Building and starting multi-container system (Backend + Frontend)..."
docker compose up -d --build

echo ""
echo "===================================================================="
echo "[SUCCESS] Containers started successfully!"
echo ""
echo "Open in browser:"
echo "  - React Dashboard:  http://localhost:5173  (or http://localhost:80)"
echo "  - FastAPI Backend:  http://localhost:8000/docs"
echo ""
echo "View live streaming logs:"
echo "  docker compose logs -f"
echo ""
echo "Stop containers:"
echo "  docker compose down"
echo "===================================================================="
