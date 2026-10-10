#!/usr/bin/env bash
# aiservice 环境变量
# ------------------------------------------------------------
# 用法（三种都行）：
#   source env.sh              # 当前 shell 生效，之后 ./start.sh
#   eval "$(./env.sh)"         # 子 shell 里生效
#   ./env.sh                   # 只打印 export 语句，自己 copy
#
# start.sh 会自动加载本文件，所以平时不用手动 source。
# 已经设置过的环境变量优先，不会被这里覆盖（想改就直接改这里）。
# ------------------------------------------------------------

# 被 source 时 export；被直接执行时打印
_ai_set() {
  if [ "${BASH_SOURCE[0]:-}" = "$0" ] || [ "$1" = "--print" ]; then
    printf 'export %s=%q\n' "$2" "$3"
  else
    export "$2=$3"
  fi
}

P="${1:-}"

# ---- 服务本身 ----
_ai_set "$P" AISERVICE_HOST      "${AISERVICE_HOST:-127.0.0.1}"
_ai_set "$P" AISERVICE_PORT      "${AISERVICE_PORT:-8100}"
_ai_set "$P" AISERVICE_LOG       "${AISERVICE_LOG:-INFO}"

# ---- 模型：本地 ollama / llama.cpp 的 OpenAI 兼容端点 ----
_ai_set "$P" LLM_PROVIDER        "${LLM_PROVIDER:-openai}"
_ai_set "$P" LLM_BASE_URL        "${LLM_BASE_URL:-http://127.0.0.1:1337/v1}"
# 本地服务不校验 key，但 provider 需要一个非空值才会启用
_ai_set "$P" LLM_API_KEY         "${LLM_API_KEY:-ollama}"
# 换成你机器上有的模型：curl http://127.0.0.1:1337/v1/models
_ai_set "$P" LLM_MODEL           "${LLM_MODEL:-LiquidAI/LFM2_5-2_6B-Q4_K_M}"
# 本地小模型比云端慢，超时放宽（超时不会 500，会自动回落到本地规则）
_ai_set "$P" LLM_TIMEOUT         "${LLM_TIMEOUT:-90}"
_ai_set "$P" LLM_TEMPERATURE     "${LLM_TEMPERATURE:-0.3}"
# 必须给生成上限：推理型模型不给 max_tokens 会一直写 chain-of-thought
_ai_set "$P" LLM_MAX_TOKENS      "${LLM_MAX_TOKENS:-2048}"
# 某些 OpenAI 兼容实现不支持 response_format，报错就设成 0。
# LFM2.5 这类推理模型带 json_object 语法会陷入死循环（实测 content 为空、
# 烧掉全部 token），所以本机默认关掉，靠服务端正则从回答里抽 JSON。
_ai_set "$P" LLM_JSON_MODE       "${LLM_JSON_MODE:-0}"

# 视觉模型：留空就用 LLM_MODEL。
# 本机 LFM2.5 是纯文本模型（没挂 mmproj），识图会失败并自动降级让前端提示补一句话。
# 换成带视觉能力的模型后，把它的 id 填在这里即可开启识图。
_ai_set "$P" LLM_VISION_MODEL    "${LLM_VISION_MODEL:-}"
