#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
cd "$PROJECT_DIR"
docker compose down
echo "PPT Creator 已停止；PostgreSQL 與模型資料仍保留在本機。"
