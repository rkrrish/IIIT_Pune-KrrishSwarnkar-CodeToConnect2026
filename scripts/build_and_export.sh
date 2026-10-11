#!/usr/bin/env bash
set -euo pipefail

echo "===================================================================="
echo " S&P 100 NLP Risk Engine - Docker Image Exporter (Linux / macOS)"
echo "===================================================================="
echo ""

echo "[*] Building all-in-one standalone Docker image: snp-nlp-engine:latest..."
docker build -t snp-nlp-engine:latest -f Dockerfile.standalone .

echo ""
echo "[*] Saving and compressing Docker image to: snp_docker_image.tar.gz..."
docker save snp-nlp-engine:latest | gzip > snp_docker_image.tar.gz

echo ""
echo "===================================================================="
echo "[SUCCESS] Portable Docker package generated:"
echo "  File: $(pwd)/snp_docker_image.tar.gz"
echo ""
echo "To replicate on ANY other machine:"
echo "  1. Copy 'snp_docker_image.tar.gz' and 'scripts/import_and_run.sh'"
echo "  2. On destination machine, run:"
echo "       bash scripts/import_and_run.sh"
echo "  3. Open http://localhost:8000 in your browser!"
echo "===================================================================="
