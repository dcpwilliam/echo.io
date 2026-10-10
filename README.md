# echo.io / aiservice

一个纯 Python 标准库实现的轻量 AI 服务，面向「一句话理解、目标/答案预测、用户状态存储、后台管理」场景。服务默认不依赖第三方包，未配置大模型时使用本地规则 Provider，接口形状保持稳定；配置 OpenAI 兼容模型后，可切换到真实 LLM 推理、视觉识别和更精细的预测。

## 快速启动

```bash
./start.sh                    # 默认 http://127.0.0.1:8100
PORT=8200 ./start.sh          # 临时换端口
python3 run.py --selftest     # 启动临时服务并跑接口自测
python3 run.py --routes       # 打印当前 35 个接口
python3 run.py --logs 50      # 查看最近 50 行日志
```

Windows 可用 `start.bat`，或直接执行 `python run.py`。

`env.sh` 集中管理环境变量，`start.sh` 会自动加载：

```bash
source env.sh
./env.sh --print
```

默认配置指向本机 OpenAI 兼容端点：

```bash
LLM_PROVIDER=openai
LLM_BASE_URL=http://127.0.0.1:1337/v1
LLM_API_KEY=ollama
LLM_MODEL=LiquidAI/LFM2_5-2_6B-Q4_K_M
LLM_TIMEOUT=120
LLM_JSON_MODE=0
```

如果没有可用 Key 或 Provider 被禁用，服务会自动回落到 `echo` 本地规则。

## 工程结构

```text
.
├─ run.py                  # CLI 入口：启动、自测、路由清单、日志查看
├─ start.sh / start.bat    # 快速启动脚本
├─ env.sh                  # 环境变量集中配置
├─ public/index.html       # 后台管理页
├─ data/                   # 运行数据：sqlite、日志、provider 配置等
├─ app/
│  ├─ api/                 # HTTP 路由层，只负责参数与响应
│  ├─ services/            # 业务服务：prompt、answer、user
│  ├─ domain/              # 本地规则、分类、日期、答案概率处理
│  ├─ prompts/             # Prompt 模板库
│  ├─ llm/                 # Provider 抽象、echo、OpenAI 兼容实现、注册表
│  ├─ storage/             # SQLite / JSON 存储后端
│  ├─ core/                # HTTP server、router、auth、logging、errors
│  └─ config.py            # 环境变量配置
└─ tools/                  # 存储测试、迁移、接口调试页面
```

分层约定：`api -> services -> domain / storage / llm`。HTTP 细节不进入领域层，模型调用不直接散落在路由里。

## 主要接口

### 运维与服务信息

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/health` | 健康检查，返回版本、运行时间、存储统计、当前 LLM Provider |
| `GET` | `/api/info` | 当前配置摘要与路由清单 |
| `GET` | `/api/logs?lines=100` | 最近日志，最多 2000 行 |

### Prompt 与 LLM

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/prompt/templates` | 模板列表、变量、是否期望 JSON |
| `POST` | `/api/prompt/render` | 只渲染模板，不调用模型 |
| `POST` | `/api/prompt/analyze` | 一句话分析：意图、领域、摘要、建议 |
| `POST` | `/api/prompt/analyze-image` | 图片理解，模型不支持视觉时返回 `needText: true` |
| `POST` | `/api/prompt/complete` | 自由补全，可传模板或直接传 `system/user` |

示例：

```bash
curl -s http://127.0.0.1:8100/api/prompt/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"三个月内减重 10 斤","use_llm":false}' | python3 -m json.tool
```

`use_llm=false` 使用本地规则；`use_llm=true` 且 Provider 可用时才调用模型。调用方也可以传 `provider` 指定某个后台配置的 Provider。

### 答案预测

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/answers/predict` | 给定问题，返回最可能的 `n` 个答案及归一化概率 |

请求：

```json
{
  "question": "明天 A 股大盘会涨还是跌？",
  "n": 3,
  "use_llm": true,
  "provider": "openai"
}
```

响应会保持统一结构：

```json
{
  "question": "明天 A 股大盘会涨还是跌？",
  "n": 3,
  "answers": [
    {"rank": 1, "answer": "震荡收涨", "probability": 0.46, "reason": "资金面和权重表现偏稳"},
    {"rank": 2, "answer": "窄幅震荡", "probability": 0.33, "reason": "缺少明确催化"},
    {"rank": 3, "answer": "冲高回落", "probability": 0.21, "reason": "上方压力可能释放"}
  ],
  "normalized": true,
  "totalProbability": 1.0,
  "provider": "openai",
  "source": "llm",
  "llmFallback": false,
  "llmFallbackReason": null
}
```

当模型不可用、超时或输出无效时，服务不会直接抛 500，而是回落本地规则，并在响应中标记 `source: "rule"` 或 `llmFallback: true`。

### 用户与状态

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/users` | 用户列表 |
| `POST` | `/api/users` | 新建用户，body: `{ id?, name?, email?, sub? }` |
| `GET` | `/api/users/{user_id}` | 用户详情 |
| `PATCH` | `/api/users/{user_id}` | 更新用户 |
| `DELETE` | `/api/users/{user_id}` | 删除用户 |
| `GET` | `/api/users/{user_id}/export` | 全量导出用户状态 |
| `POST` | `/api/users/{user_id}/import` | 导入状态，`mode: replace | merge` |
| `GET` | `/api/state` | 兼容旧客户端 `pullState` |
| `PUT` | `/api/state` | 兼容旧客户端 `pushState` |

`/api/state` 默认通过 `Authorization: Bearer <token>` 派生 `user_id`；本地调试可使用 `?user_id=xxx`。

### 登录、后台与 Provider 管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/api/auth/login` | 后台登录，成功写入 HttpOnly cookie |
| `POST` | `/api/auth/logout` | 登出 |
| `GET` | `/api/auth/me` | 当前登录用户 |
| `GET` | `/api/admin/users` | 用户摘要，需登录 |
| `GET` | `/api/admin/users/{user_id}` | 用户等级、金币、投票记录，需登录 |
| `POST` | `/api/admin/users/{user_id}/level` | 设置等级 |
| `POST` | `/api/admin/users/{user_id}/coins` | 设置金币 |
| `GET/POST` | `/api/admin/users/{user_id}/votes` | 查看或追加投票记录 |
| `GET/POST` | `/api/admin/providers` | Provider 列表 / 新增 |
| `GET/PUT/DELETE` | `/api/admin/providers/{id}` | Provider 详情 / 更新 / 删除 |
| `POST` | `/api/admin/providers/{id}/default` | 设为默认 Provider，实时生效 |
| `POST` | `/api/admin/providers/{id}/test` | 联通性测试 |

后台页面：`http://127.0.0.1:8100/`。默认账号密码为 `admin/admin`，生产环境请设置：

```bash
AISERVICE_ADMIN_USER=...
AISERVICE_ADMIN_PASS=...
```

Provider 配置持久化在 `data/llm_providers.json`，后台修改后下一次请求立即生效，无需重启。

## Agent 工作模式

当前服务里的 agent 更接近一个「可降级的决策流水线」，不是单一 prompt 直连模型：

1. 接收输入：来自 `/api/prompt/analyze`、`/api/answers/predict`、`/api/prompt/analyze-image` 等接口。
2. 准备上下文：读取用户状态、已有目标摘要或问题参数，渲染 `app/prompts/templates.py` 中的模板。
3. 选择执行器：根据请求中的 `provider` 或注册表默认值，选择 `echo` 本地规则或 OpenAI 兼容 Provider。
4. 约束输出：提示词要求 JSON 字段、枚举值、数量和可操作建议。
5. 清洗与校验：服务层会检测占位文本、缺字段、非法概率、截断 JSON 等问题。
6. 兜底：模型不可用或输出不合格时回退到本地规则，保持响应结构稳定。
7. 返回结果：响应中标出 `provider`、`source`、`llmFallback`，方便前端展示和日志追踪。

这种模式保证了三件事：离线可跑、模型可替换、前端不用因为模型失败写复杂分支。

## LLM 交互机制

LLM 抽象在 `app/llm/`：

- `LLMProvider` 定义统一的 `complete`、`complete_json`、`describe_image` 接口。
- `EchoProvider` 是本地规则实现，永远可用，不联网。
- `OpenAICompatibleProvider` 使用标准库 `urllib` 调用 `/chat/completions`，兼容 DeepSeek、通义、Moonshot、本地 Ollama/llama.cpp 等 OpenAI 风格服务。
- `registry.py` 维护 Provider 列表、默认 Provider、脱敏展示、持久化和实时切换。

JSON 输出采用宽松解析：能处理代码围栏、前后废话、部分截断内容；解析失败则返回 `raw` 并交由服务层判断是否回退。

视觉输入走 `describe_image`。如果模型不支持图片，接口返回：

```json
{
  "ok": false,
  "needText": true,
  "reason": "no-vision",
  "hint": "当前模型不支持识图，补一句话说明"
}
```

前端可据此要求用户补充文字，而不是把失败暴露成服务错误。

## 未来规划：可插拔 Skill

下一阶段可以把「预测」和「选择建议」从固定 prompt 升级为可插拔 skill 系统，让不同领域使用不同的证据、模型和评估方式。

建议方向：

- Skill 注册表：定义 `id / name / domain / inputs / outputs / provider / confidence`，支持按问题类型自动选择 skill。
- 预测 Skill：例如市场走势、目标达成率、学习计划完成概率、用户流失风险，各自维护专用 prompt、特征抽取和概率校准。
- 决策 Skill：对多个候选行动做成本、收益、风险、时间窗评分，返回排序建议和解释。
- 数据源 Skill：接入历史记录、外部行情、日历、账单、运动数据等，让预测不只依赖语言模型常识。
- 评估与回放：保存每次预测的输入、输出、实际结果和误差，用于校准概率与淘汰低质量 skill。
- 策略编排：先用轻量规则判断领域，再路由到专用 skill；高风险或低置信度时触发多 Provider 交叉验证。

目标是让系统从「通用 LLM 猜测」进化到「按领域调用最合适的工具、数据和模型」，从而给出更精确的预测和更可信的选择建议。

## 常用调试命令

```bash
python3 run.py --routes
python3 run.py --selftest
python3 run.py --logs 100

curl -s http://127.0.0.1:8100/health | python3 -m json.tool
curl -s http://127.0.0.1:8100/api/prompt/templates | python3 -m json.tool
curl -s http://127.0.0.1:8100/api/answers/predict \
  -H 'Content-Type: application/json' \
  -d '{"question":"这个项目下一步最该做什么？","n":3,"use_llm":false}' | python3 -m json.tool
```

## 部署说明

Docker 相关文件已包含在根目录：

```bash
./docker-build.sh
./docker-up.sh
docker compose up
```

数据默认写入 `data/`。如果需要持久化部署，请挂载该目录，并显式设置管理员账号、LLM Provider、日志级别和数据目录。
