#!/usr/bin/env bash
set -euo pipefail

echo "===================================================================="
echo " S&P 100 NLP Risk Engine - One-Click Launcher (Linux / macOS)"
echo "===================================================================="
echo ""

ARCHIVE_FILE=""
if [ -f "snp_docker_image.tar.gz" ]; then
    ARCHIVE_FILE="snp_docker_image.tar.gz"
elif [ -f "snp_docker_image.tar" ]; then
    ARCHIVE_FILE="snp_docker_image.tar"
fi

if [ -z "$ARCHIVE_FILE" ]; then
    echo "[!] Neither 'snp_docker_image.tar.gz' nor 'snp_docker_image.tar' was found."
    echo "    Please place the archive file in the current working directory."
    exit 1
fi

echo "[*] Loading Docker image from $ARCHIVE_FILE..."
if [[ "$ARCHIVE_FILE" == *.gz ]]; then
    gzip -dc "$ARCHIVE_FILE" | docker load
else
    docker load -i "$ARCHIVE_FILE"
fi

echo ""
echo "[*] Cleaning up any previous 'snp-engine' container..."
docker stop snp-engine 2>/dev/null || true
docker rm snp-engine 2>/dev/null || true

echo ""
echo "[*] Starting S&P 100 NLP Risk Engine container..."
docker run -d --name snp-engine -p 8000:8000 snp-nlp-engine:latest

echo ""
echo "===================================================================="
echo "[SUCCESS] Application successfully launched!"
echo ""
echo "Access the full interactive system:"
echo "  - Web Dashboard:     http://localhost:8000"
echo "  - Swagger API Docs:  http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  - Live logs:  docker logs -f snp-engine"
echo "  - Stop:       docker stop snp-engine"
echo "===================================================================="
