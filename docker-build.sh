#!/usr/bin/env bash
# 仅构建 aiservice 镜像（不启动）
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 构建 aiservice 镜像 ..."
docker compose build
echo "==> 完成。运行 ./docker-up.sh 一键启动，或 docker compose up -d"
