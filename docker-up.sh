#!/usr/bin/env bash
# 一键启动 aiservice（Docker Compose 构建 + 后台运行 + 等探活）
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 构建并启动 aiservice 容器 ..."
docker compose up -d --build

echo "==> 等待服务就绪（最多 30 秒）..."
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8100/health >/dev/null 2>&1; then
    echo "==> aiservice 已就绪：http://127.0.0.1:8100"
    echo
    curl -fsS http://127.0.0.1:8100/health
    echo
    echo "==> 查看日志：docker compose logs -f aiservice"
    echo "==> 停止服务：docker compose down"
    exit 0
  fi
  sleep 1
done

echo "!! 服务未在 30 秒内就绪，打印最近日志："
docker compose logs --tail=50 aiservice
exit 1
