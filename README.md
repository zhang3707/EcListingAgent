# EcListingAgent

> 电商商品上下架智能 Agent —— 覆盖 **ERP 素材库检索 → SKU / 价格匹配 → 多店铺上架 → 飞书多维表格归档** 全流程。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](docker-compose.yml)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2%2B-ff6b6b.svg)](https://github.com/langchain-ai/langgraph)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688.svg)](https://fastapi.tiangolo.com/)

不依赖平台官方 API、不使用传统 RPA，采用 **浏览器深度定制 + LangGraph 决策驱动** 的拟人化方案，配套 YOLOv8 滑块验证码识别与人机协同短信验证，实现端到端自动化上下架。

---

## 🛠️ 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 编排 | LangGraph | 状态机式 Agent 编排，支持分支 / 重试 / interrupt 挂起恢复 |
| 浏览器 | Playwright | Chromium 自动化，指纹隔离 + 拟人化行为模拟 |
| 验证码 | YOLOv8 (Ultralytics) | 滑块缺口检测，支持 CV 降级 |
| 接口 | FastAPI + Uvicorn | 任务提交 / 查询 / 回调 / 风控 / 健康检查 |
| 存储 | PostgreSQL | 任务 / 日志 / LangGraph Checkpointer 持久化 |
| 对象存储 | MinIO | 商品图片素材存储与预签名下载 |
| 归档 | 飞书多维表格 | 任务状态 / SKU 明细 / 日志自动同步 |
| 容器 | Docker + Compose | 多店铺隔离编排，单店铺单容器 |

---

## ✨ 核心特性

| 能力 | 说明 |
|------|------|
| **拟人化浏览器** | Playwright + 指纹隔离 + 行为模拟，规避自动化检测 |
| **滑块验证码识别** | YOLOv8 缺口检测，≤2px 命中率 100%，支持 CV 降级 |
| **多平台适配** | 淘宝 / 拼多多 / 抖音 / 京东，配置化选择器与字段映射 |
| **LangGraph 编排** | 状态机式 Agent，支持分支判断、重试、异常降级、interrupt 挂起恢复 |
| **风控熔断** | 页面级风控信号检测 + 失败计数阈值，触发即终止并告警 |
| **多店铺隔离** | 单店铺单容器，独立浏览器 profile 与指纹，互不干扰 |
| **飞书归档** | 任务状态 / 日志 / SKU 明细自动同步多维表格，支持死信补偿 |
| **人机协同** | 短信验证码通过飞书通知人工回复，恢复挂起任务 |

---

## 🏗️ 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                         接口层 (FastAPI)                       │
│  任务提交 / 查询 / 取消 / 回调  ·  店铺管理  ·  风控  ·  健康检查  │
└───────────────┬──────────────────────────────┬───────────────┘
                │ inline 模式                    │ worker 模式（DB 调度）
┌───────────────▼──────────────┐  ┌─────────────▼──────────────┐
│     编排层 (LangGraph)        │  │   单店铺 Worker（容器隔离）   │
│  retrieve → match → list →    │  │   轮询 DB 领取本店铺任务      │
│  captcha → risk → archive     │  │   串行执行，避免风控          │
└───────┬───────────┬───────────┘  └─────────────┬──────────────┘
        │           │                            │
┌───────▼────┐ ┌────▼─────┐  ┌───────────────────▼────────────┐
│  Skill 层   │ │ 引擎层    │  │           数据层                 │
│  6 个核心    │ │ browser  │  │  PostgreSQL（任务/日志）         │
│  Skill      │ │ stealth  │  │  MinIO（商品素材）               │
│             │ │ captcha  │  │  LangGraph Checkpointer（挂起）  │
└─────────────┘ └──────────┘  └────────────────────────────────┘
```

**分层职责**

- **编排层** `agent/` — LangGraph 状态机：节点编排、路由分支、重试与降级
- **Skill 层** `skills/` — 6 个核心能力（素材检索、SKU 匹配、上架、验证码、风控、归档）
- **引擎层** `engine/` — 浏览器定制、指纹隔离、拟人化、验证码识别
- **数据层** `data/` — ORM、仓储、MinIO、Checkpointer
- **接口层** `api/` — FastAPI 路由
- **集成层** `integrations/` — 飞书多维表格、ERP 对接

---

## 📁 目录结构

```
agent/              LangGraph 编排层（state / graph / nodes / routes / runner / worker）
skills/             Skill 层（base + platforms/{taobao,pinduoduo,douyin,jingdong}）
engine/             引擎层（browser / stealth / fingerprint / humanize / captcha）
data/               数据层（db / models / minio + repositories）
integrations/       外部对接（feishu / erp）
api/                FastAPI 接口层（server + routes/{tasks,shops,ops}）
config/             配置（settings + shops/*.yaml + feishu.yaml）
scripts/            运维脚本（init_db / train_slider / gen_slider_dataset / eval_slider）
tests/              测试（test_skills / test_engine / test_api / test_graph）
Dockerfile          容器镜像（python:3.11-slim + Playwright Chromium）
docker-compose.yml  多店铺隔离编排（postgres / minio / api / worker-*）
entrypoint.sh       容器角色化入口（ROLE=api / worker / migrate）
```

---

## 🚀 快速开始（本地开发）

### 前置要求

- Python ≥ 3.11
- Node.js（Playwright 浏览器下载）
- Docker & Docker Compose（用于 PostgreSQL + MinIO）

### 1. 安装依赖

```bash
pip install -e ".[dev]"
playwright install chromium
```

### 2. 配置环境

```bash
cp .env.example .env          # 填写数据库、MinIO、飞书、店铺账号
```

编辑 `config/shops/shop_*.yaml` 配置各平台店铺的后台地址、选择器、字段映射；
编辑 `config/feishu.yaml` 配置飞书应用与多维表格。

### 3. 启动依赖服务

```bash
docker compose up -d postgres minio
```

### 4. 初始化数据库

```bash
python scripts/init_db.py
```

### 5. 启动 API

```bash
uvicorn api.server:app --reload --port 8000
```

访问交互式文档：http://localhost:8000/docs

---

## 🐳 Docker 部署（多店铺隔离）

一键启动全部服务（含 API + worker 容器）：

```bash
# 构建镜像
docker compose build

# 启动基础设施 + API + 各店铺 worker
docker compose up -d postgres minio api worker-taobao worker-pinduoduo

# 查看某店铺 worker 日志
docker compose logs -f worker-taobao
```

**服务拓扑**

| 服务 | 角色 | 说明 |
|------|------|------|
| `postgres` | 基础设施 | 任务持久化 + LangGraph checkpointer |
| `minio` | 基础设施 | 商品图片素材存储 |
| `api` | `ROLE=api` | FastAPI 接口层，启动前自动建表 |
| `worker-taobao` | `ROLE=worker` | 淘宝店铺任务执行，独立 profile 卷 |
| `worker-pinduoduo` | `ROLE=worker` | 拼多多店铺任务执行，独立 profile 卷 |

新增店铺只需在 `docker-compose.yml` 复制 worker 段并修改 `TARGET_SHOP` 与卷名。

---

## 📡 API 接口

### 任务管理

```bash
# 创建上架任务
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"product_code":"P100001","target_shop":"shop_taobao","callback_url":"https://biz.example.com/cb"}'

# 查询任务状态
curl http://localhost:8000/api/tasks/{task_id}

# 任务列表（可按状态过滤）
curl "http://localhost:8000/api/tasks?status=待执行&limit=20"

# 取消任务
curl -X POST http://localhost:8000/api/tasks/{task_id}/cancel

# 任务统计
curl http://localhost:8000/api/tasks/stats/summary
```

### 短信验证码人机协同

任务触发短信验证时会挂起，运营人员通过飞书收到通知后回复验证码恢复：

```bash
curl -X POST http://localhost:8000/api/tasks/{task_id}/resume \
  -H "Content-Type: application/json" \
  -d '{"code":"123456"}'
```

### 店铺与风控

```bash
# 店铺列表
curl http://localhost:8000/api/shops

# 店铺详情（含风控状态、今日登录次数）
curl http://localhost:8000/api/shops/shop_taobao

# 查询/重置风控状态
curl http://localhost:8000/api/shops/shop_taobao/risk
curl -X POST http://localhost:8000/api/shops/shop_taobao/risk/reset

# 配置热重载
curl -X POST http://localhost:8000/api/shops/reload
```

### 运维

```bash
# 详细健康检查（DB / MinIO / 飞书配置）
curl http://localhost:8000/api/health/detailed

# 触发飞书归档补偿（重试失败记录）
curl -X POST http://localhost:8000/api/feishu/compensate
```

---

## ⚙️ 配置

### 环境变量（`.env`）

见 `.env.example`，包含：`PG_DSN`、`MINIO_*`、`FEISHU_APP_*`、各平台账号密码、`TARGET_SHOP`。

### 店铺配置（`config/shops/shop_*.yaml`）

每店铺一个 YAML，定义：后台地址、登录选择器、风控信号、上架字段映射、价格策略。敏感字段支持 `${ENV_VAR}` 占位符从环境变量注入。

### 飞书配置（`config/feishu.yaml`）

飞书应用凭证 + 多维表格 token + 字段映射。

---

## 🧠 滑块模型训练

内置 YOLOv8 缺口检测模型，支持合成数据集生成、训练、评估全流程：

```bash
# 1. 生成合成数据集（含双类别标注 + 亮度随机化）
python scripts/gen_slider_dataset.py

# 2. 训练（生产级，含数据增强 + 早停）
python scripts/train_slider.py --epochs 100 --batch 8 --workers 2 --patience 20

# 3. 评估（≤2px 命中率目标 ≥90%）
python scripts/eval_slider.py --model data_persist/slider_gap_yolov8n/weights/best.pt
```

当前模型指标：precision 0.999 / recall 1.0 / mAP50-95 0.995，≤2px 命中率 100%。

---

## 🧪 测试

```bash
# 全量测试
pytest

# 仅 API 接口测试
pytest tests/test_api/ -v

# 语法校验
python -m compileall agent skills engine data integrations api config scripts
```

---

## ⚠️ 风险与合规

- 仅用于**自身合法店铺**的运营辅助。
- 拟人化操作可降低风控概率但**无法完全规避**，建议先用小号验证。
- 禁止用于恶意铺货、侵权上架、刷单等违规行为。
- 使用前请阅读各平台服务条款，自行承担合规风险。

---

## 📌 项目状态

| 模块 | 状态 | 说明 |
|------|------|------|
| 编排层（LangGraph） | ✅ 可用 | 节点编排 / 路由 / 重试 / interrupt 挂起恢复 |
| 引擎层（浏览器 / 指纹 / 拟人化） | ✅ 可用 | Playwright 定制 + 反检测 |
| 滑块验证码识别 | ✅ 可用 | YOLOv8 模型已训练，≤2px 命中率 100% |
| 风控熔断 | ✅ 可用 | 页面信号检测 + 失败计数阈值 |
| 飞书归档 | ✅ 可用 | upsert + 字段映射 + 死信补偿 |
| API 接口层 | ✅ 可用 | 任务 / 店铺 / 风控 / 健康 / 运维 |
| 多平台选择器 | 🔧 待校准 | 淘宝 / 拼多多 / 抖音 / 京东 结构已就绪，需按真实后台 DOM 校准 |
| 容器化部署 | ✅ 可用 | Docker Compose 多店铺隔离 |

> 多平台选择器当前为配置化骨架，投产前需对照各平台真实后台 DOM 校准选择器与字段映射。

---

## 🤝 贡献

欢迎提交 Issue 与 Pull Request。提交前请：

1. 确保改动不违反各平台服务条款，仅用于自身合法店铺运营。
2. 新增功能请附带测试（`pytest`）。
3. 涉及选择器变更时，同步更新对应 `config/shops/shop_*.yaml`。
4. 遵循现有代码风格与目录约定。

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。使用前请阅读许可证全文与上方「风险与合规」说明。
