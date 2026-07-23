#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${PROJECT_DIR}"
docker compose down
echo "PPT Creator 已停止；PostgreSQL 與模型資料仍保留在本機。"
