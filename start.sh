#!/usr/bin/env bash
# aiservice 快速启动（macOS / Linux）
#
#   ./start.sh                 默认 127.0.0.1:8100
#   PORT=8200 ./start.sh
#   ./start.sh --host 0.0.0.0  对外可访问（真机调试用）
#   PYTHON_BIN=/path/to/python3 ./start.sh
#
set -euo pipefail
cd "$(dirname "$0")"

# 加载 env.sh（已存在的环境变量优先）
if [ -f env.sh ]; then . ./env.sh; fi

HOST="${AISERVICE_HOST:-127.0.0.1}"
PORT="${PORT:-${AISERVICE_PORT:-8100}}"

pick_python() {
  if [ -n "${PYTHON_BIN:-}" ] && command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "$PYTHON_BIN"; return
  fi
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 \
       && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' >/dev/null 2>&1; then
      echo "$c"; return
    fi
  done
  echo ""
}

PY="$(pick_python)"
if [ -z "$PY" ]; then
  echo "✗ 没找到 Python 3.8+。可显式指定：PYTHON_BIN=/path/to/python3 ./start.sh" >&2
  exit 1
fi

mkdir -p "${AISERVICE_DATA_DIR:-data}"

echo "────────────────────────────────────────"
echo " aiservice · Timeline 的 Python 侧服务"
echo "────────────────────────────────────────"
echo " Python   : $($PY -V 2>&1)"
echo " 监听     : http://$HOST:$PORT"
echo " 数据目录 : ${AISERVICE_DATA_DIR:-$(pwd)/data}"
echo " LLM      : ${LLM_PROVIDER:-echo} @ ${LLM_BASE_URL:-（未设置）} · ${LLM_MODEL:-（未设置）}"
echo "────────────────────────────────────────"
echo

exec "$PY" run.py --host "$HOST" --port "$PORT" "$@"
