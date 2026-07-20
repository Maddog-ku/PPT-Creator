#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
cd "$PROJECT_DIR"

if ! docker info >/dev/null 2>&1; then
  echo "請先啟動 Docker Desktop。"
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  if [[ "$(uname -s)" == "Darwin" ]]; then
    echo "正在啟動本機 Ollama…"
    open -a Ollama
  fi
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

if ! curl -fsS http://127.0.0.1:11434/api/version >/dev/null 2>&1; then
  echo "無法連線 Ollama，請確認 Ollama 已安裝並啟動。"
  exit 1
fi

echo "正在啟動 PPT Creator；首次執行會下載缺少的本機模型…"
docker compose up -d --build
docker compose ps
echo "PPT Creator 已啟動：http://localhost:3000"
