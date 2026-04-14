# AiOps 智能运维平台

<p align="center">
  <strong>基于 Django + Channels 的现代化智能运维平台</strong><br>
  <em>从「被动运维」到「AI 驱动的智能辅助」</em>
</p>

---

## 📌 项目来源与衍生关系

> **本项目基于 [Gitee 仓库 `charyelo-air/aiops`](https://gitee.com/charyelo-air/aiops) 进行二次开发与深度增强。**

| 项目 | 说明 |
|------|------|
| **上游仓库** | [https://gitee.com/charyelo-air/aiops](https://gitee.com/charyelo-air/aiops) |
| **上游定位** | 基于 Django + Channels 的智能运维平台，集成 CMDB、WebSSH、K8s 管理及 AI 诊断 |
| **本仓库定位** | 在上游基础上，**新增完整 AIOps 监控告警体系**，包括异常检测、AI 根因分析（Qwen3）、告警关联聚类、自动修复引擎、知识库推荐等核心能力 |

### 主要增强内容

- 🧠 **AIOps 智能监控模块** (`monitoring/`) — 全新开发的核心监控子系统
- 🔍 **多算法异常检测** — Z-Score / IQR / 移动平均 / 变化率 / 复合投票等 6+ 种检测算法
- 🤖 **Qwen3 AI 根因分析** — 基于阿里云通义千问的智能诊断引擎（OpenAI 兼容接口）
- 🔗 **告警关联聚类** — 自动识别同一根因引发的级联告警
- 🛠️ **自动修复引擎** — 危险操作确认 + 自动执行修复脚本
- 📚 **运维知识库** — AI 智能推荐匹配的 Runbook 条目
- 📊 **AIOps Dashboard** — 自定义 Admin Dashboard，实时展示 AI 诊断数据、根因分布、趋势预测
- ⚙️ **`.env` 环境变量管理** — 统一配置管理，支持 Docker 部署
- 💾 **PostgreSQL 18 支持** — 双数据库模式（SQLite 开发 / PostgreSQL 生产）

---

## ✨ 核心功能

### 🤖 AIOps 智能监控（本仓库核心增强）

| 能力 | 说明 |
|------|------|
| **异常检测引擎** | 内置 Z-Score、IQR 四分位、移动平均、变化率、复合投票、动态基线等 6+ 种检测算法，可插拔扩展 |
| **AI 根因分析** | 告警触发后自动调用 Qwen3（通义千问）进行智能诊断，输出根因分类、置信度评分、修复建议和紧急程度评估 |
| **告警规则系统** | 支持静态阈值、动态基线、趋势检测、复合条件、消失检测等多种规则类型，P0-P3 分级 |
| **告警关联聚类** | 基于时间窗口和服务拓扑的 Correlator，自动将级联告警聚合为告警簇，减少告警风暴 |
| **通知渠道管理** | 多渠道通知（钉钉 / 微信 / 邮票 / Webhook），支持静默规则和升级策略（Escalation Policy） |
| **自动修复引擎** | 匹配告警级别自动执行预定义的修复动作（脚本执行 / 服务重启 / 磁盘清理 / 扩容），危险操作需人工确认 |
| **运维知识库 (Runbook)** | 结构化存储故障处理经验，AI 根据当前告警智能推荐匹配的知识条目 |
| **健康度评分** | 多维度服务器健康打分（CPU / 内存 / 磁盘 / 网络 / 可用性），支持历史追踪 |
| **服务拓扑追踪** | 维护服务间依赖关系图，支持影响分析和故障传播路径可视化 |
| **数据导出** | Admin 后台支持 CSV / Excel 格式批量导出所有监控数据 |

### ☸️ Kubernetes 管理（继承自上游）

- 多集群 KubeConfig 导入与管理
- 全资源覆盖：Pod / Deployment / StatefulSet / DaemonSet / Service / Ingress / ConfigMap / Secret / PV / PVC / StorageClass
- Web Shell 容器终端 + 实时日志查看
- YAML 智能审计（提交前 AI 安全检查）
- 可视化扩缩容

### 🖥️ 资产与监控 CMDB（继承并增强）

- **混合采集**：Agentless SSH 远程拉取 + Agent 推送上报（支持内网穿透）
- **实时指标**：CPU / 内存 / 磁盘 / 网络 I/O / 负载仪表盘
- **WebSSH**：xterm.js + WebSocket，SFTP 文件传输，全量操作录像，高危操作预警
- **云同步**：阿里云 / 腾讯云 ECS 实例一键同步
- **Java 诊断**：在线 jstack 线程堆栈分析

### 🛠️ 运维工具（继承自上游）

- 脚本管理：Shell / Python 脚本库，AI 代码优化，批量并发执行
- RBAC 权限：角色 → 服务器分组，精确到数据级的权限控制
- SSL 证书管理：自动发现、到期提醒、一键续签

---

## 🛠️ 技术栈

| 类别 | 技术 |
|------|------|
| **后端框架** | Python 3.9+, Django 4.x+ |
| **异步通信** | Django Channels 3.0, channels-redis, Daphne ASGI Server |
| **任务队列** | Celery 5.6 + eventlet, Redis Broker |
| **定时调度** | APScheduler + Celery Beat |
| **AI 引擎** | OpenAI Python SDK 2.9（兼容 Qwen3 / DeepSeek / GPT 等） |
| **异常检测** | NumPy, SciPy, scikit-learn, statsmodels |
| **SSH 交互** | Paramiko |
| **K8s 交互** | Kubernetes Python Client 34.x |
| **数据库** | SQLite（开发）/ PostgreSQL 18（生产），Django ORM |
| **缓存/消息** | Redis |
| **前端** | Django Templates, Bootstrap 4, ECharts 5, Xterm.js, Ace Editor |
| **环境管理** | python-dotenv (.env 文件支持) |

---

## 🚀 快速开始

### 环境要求

- Python 3.9+
- Redis（用于 Celery + WebSocket Channels）
- PostgreSQL 18（生产环境可选，默认使用 SQLite）

### 1. 克隆仓库

```bash
git clone <your-repo-url>
cd aiops
```

### 2. 创建虚拟环境并安装依赖

```bash
# 创建虚拟环境（推荐 conda 或 venv）
conda create -n aiops python=3.12 -y
conda activate aiops

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# 从模板复制环境配置文件
cp .env.example .env

# 编辑 .env，填入实际配置值
# 必须配置项：
#   - DJANGO_SECRET_KEY: Django 密钥
#   - DB_*: 数据库连接（留空则使用 SQLite）
#   - REDIS_*: Redis 连接（Celery + WebSocket 需要）
#   - QWEN_API_KEY: AI 诊断引擎密钥
```

**`.env` 关键配置说明**：

```bash
# === 数据库（二选一）===
DB_ENGINE=                    # 留空=SQLite(开发), postgresql=PostgreSQL(生产)
DB_NAME=aiops_db
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432

# === Redis（必配，Celery + WebSocket 需要）===
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=

# === AI 诊断引擎（Qwen3 推荐）===
QWEN_API_KEY=sk-your-key-here
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_DIAGNOSE_MODEL=qwen-plus    # qwen-turbo / qwen-plus / qwen-max

# 也支持其他 OpenAI 兼容接口：
# OPENAI_API_KEY=sk-xxx
# OPENAI_BASE_URL=https://api.openai.com/v1
```

### 4. 初始化数据库

```bash
python reset_db.py
python manage.py createsuperuser
```

### 5. 启动服务

```bash
# 方式 A: 使用 runserver（开发调试，不支持 WebSocket）
python manage.py runserver

# 方式 B: 使用 Daphne（完整功能，支持 WebSocket）
daphne -b 0.0.0.0 -p 8000 ops_platform.asgi:application
```

### 6. 启动后台进程（按需）

```bash
# 启动 Celery Worker（异步任务：AI 诊断、告警处理）
celery -A ops_platform worker -l info -P eventlet

# 启动监控采集 Agent
python manage.py run_agent

# K8s 集群数据采集
python manage.py collect_k8s
```

### 7. 访问系统

- **主控台**: http://localhost:8000/
- **AIOps 监控中心**: http://localhost:8000/monitoring/admin/

---

## 📁 项目结构

```
aiops/
├── .env                          # 环境变量配置（含敏感信息，不提交 Git）
├── .env.example                  # 环境变量模板
├── .gitignore                    # Git 忽略规则
├── requirements.txt              # Python 依赖
├── manage.py                     # Django 管理入口
├── reset_db.py                   # 数据库重置脚本
│
├── ops_platform/                 # 核心 Django 项目配置
│   ├── settings.py               # 主设置文件（加载 .env，双数据库支持）
│   ├── urls.py                   # URL 路由（含自定义 Admin Site）
│   ├── asgi.py                   # ASGI 配置（Channels WebSocket）
│   ├── wsgi.py                   # WSGI 配置
│   └── celery.py                 # Celery 配置
│
├── monitoring/                   # ★ AIOps 智能监控模块（本仓库核心增强）
│   ├── models.py                 # 数据模型（AlertRule, AlertEvent, AnomalyHistory...）
│   ├── admin.py                  # 自定义 Admin（Dashboard + 导出 + AIOps 展示）
│   ├── ai_callback.py            # AI 诊断回调（Qwen3 根因分析引擎）
│   ├── anomaly_detector.py       # 异常检测算法（ZScore/IQR/MovingAvg/RateOfChange...）
│   ├── anomaly_marker.py         # 异常标记器
│   ├── tasks.py                  # Celery 异步任务
│   ├── utils.py                  # 工具函数
│   │
│   ├── engine/rule_evaluator.py  # 规则评估引擎
│   ├── correlation/correlator.py # 告警关联聚类器
│   ├── aggregation/alert_aggregator.py  # 告警聚合
│   ├── notification/channel_manager.py  # 多渠道通知
│   ├── escalation/escalator.py   # 告警升级策略
│   ├── remediation/remediation_engine.py  # 自动修复引擎
│   ├── health/scorer.py          # 健康度评分
│   ├── topology/tracker.py       # 服务拓扑追踪
│   ├── runbook/recommender.py    # 知识库智能推荐
│   ├── agent/push_api.py         # Agent 数据推送 API
│   └── websocket/consumers.py    # WebSocket 实时推送
│
├── cmdb/                         # 资产管理模块（CMDB）
│   ├── models.py                 # 服务器、账号、分组模型
│   ├── admin.py                  # CMDB Admin
│   ├── consumers.py              # WebSocket（WebSSH/SFTP）
│   └── views.py                  # 视图（服务器 CRUD / SSH / 审计 / Java 诊断）
│
├── k8s_manager/                  # Kubernetes 集群管理
│   ├── models.py                 # 集群、Pod、Node 模型
│   ├── admin.py                  # K8s Admin
│   ├── consumers.py              # WebSocket（容器终端/日志）
│   └── views.py                  # 视图（集群管理 / 资源 CRUD）
│
├── system/                       # 系统管理模块
│   ├── models.py                 # 用户、角色模型
│   ├── auth_backend.py           # LDAP 认证后端
│   └── validators.py             # 密码复杂度验证
│
├── script_manager/               # 脚本管理模块
├── ai_ops/                       # AI 对话平台模块
├── agent/                        # K8s Agent（Node 级采集器）
│
├── templates/                    # 前端模板
│   ├── admin/index.html          # ★ AIOps 智能监控 Dashboard（Qwen3 驱动）
│   ├── base.html                 # 全局布局
│   ├── cmdb/                     # CMDB 相关模板
│   ├── k8s/                      # K8s 相关模板
│   └── ...                       # 其他模块模板
│
├── scripts/migration/            # 数据库迁移脚本
└── docs/                         # 项目文档
```

---

## ⚙️ 初始化配置指南（首次运行必读）

### 1. 配置 AI 诊断引擎

编辑 `.env` 文件中的 AI 相关配置：

```bash
# 推荐方案：阿里云通义千问 Qwen3
QWEN_API_KEY=sk-xxxxxxxxxxxxx
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_DIAGNOSE_MODEL=qwen-plus

# 备选方案：SiliconFlow 代理（兼容 OpenAI API）
QWEN_API_KEY=sk-xxxxxxxxxxxxx
QWEN_BASE_URL=https://api.siliconflow.cn/v1
AI_DIAGNOSE_MODEL=Qwen/Qwen3.5-9B

# 备选方案：DeepSeek
OPENAI_API_KEY=sk-xxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com
AI_DIAGNOSE_MODEL=deepseek-chat
```

### 2. 录入服务器

进入 **资产管理 → 主机列表 → 手动录入**

填写 IP、SSH 端口、账号密码后，可选择：
- **Agentless 模式**：直接通过 SSH 远程拉取指标
- **Agent 模式**：勾选服务器后点击「批量安装 Agent」

### 3. 配置监控规则

进入 **AIOps 监控中心 → 预警规则**，创建告警规则：

| 字段 | 说明 |
|------|------|
| 名称 | 规则唯一标识 |
| 类型 | threshold(静态阈值) / baseline(动态基线) / trend(趋势) / anomaly(异常检测) |
| 级别 | P0致命 / P1严重 / P2警告 / P3提示 |
| 目标指标 | cpu_usage / mem_usage / disk_usage / load_1min / net_in / net_out |
| 条件配置 | 如 `{"operator":"gt","value":90}` 表示 CPU > 90% 时触发 |

### 4. 配置 K8s 集群（可选）

进入 **K8s 容器管理 → 集群配置**，粘贴 `~/.kube/config` 内容即可纳管。

---

## 🔌 API 接口

监控模块提供 REST API（位于 `/api/monitoring/`）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/monitoring/push` | Agent 上报服务器指标数据 |
| GET | `/api/monitoring/alerts` | 查询告警事件列表 |
| GET | `/api/monitoring/anomalies` | 查询异常检测记录 |
| GET | `/api/monitoring/health` | 查询服务器健康度评分 |

---

## 📊 AIOps Dashboard 功能一览

访问 `/monitoring/admin/` 即可看到以下 AI 驱动的监控面板：

```
┌─────────────────────────────────────────────────────┐
│  🧠 Qwen3 AI 引擎运行中                              │
│  通义千问驱动 · 异常检测 · 告警聚合 · 根因分析 · 自愈修复 │
├──────────┬──────────┬──────────┬──────────┬─────────┤
│ 服务器总数 │ 活跃告警 │ 启用规则 │ 今日告警 │ 平均健康度│
├──────────┴──────────┴──────────┴──────────┴─────────┤
│  AI 诊断次数 │ 平均置信度 │ 活跃告警簇 │ 自动修复率   │
├─────────────────────────────────────────────────────┤
│  🧠 AI 智能诊断 [Qwen3]                             │
│  ├─ server-01 · CPU usage     [85%] 资源不足        │
│  │   分析: CPU持续升高，接近阈值...                  │
│  │   ⏱ 5分钟前  ⚡ urgent                           │
│  ├─ server-03 · MEM usage     [72%] 配置错误        │
│  └─ ...                                               │
├─────────────────────────────────────────────────────┤
│  📈 异常检测算法分布  │  🎯 根因分类统计             │
│  📉 移动平均 45%     │  💾 资源不足 35%             │
│  📊 Z-Score   30%     │  ⚙️ 配置错误 25%            │
│  📐 IQR四分位 15%     │  🌐 网络    20%             │
│  ...                │  ...                         │
├─────────────────────────────────────────────────────┤
│  🔄 自动修复时间线  │  📚 知识库智能推荐            │
│  ✅ 清理日志 10s     │  🔗 CPU飙高处理方案           │
│  ✅ 重启Nginx 30s    │  💾 内存泄漏排查步骤          │
│  ❌ 扩容失败          │  🌐 网络抖动应对策略          │
└─────────────────────────────────────────────────────┘
```

---

## 🤝 贡献方式

欢迎贡献代码、文档或提出建议！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/amazing-feature`
3. 提交更改：`git commit -m 'Add amazing feature'`
4. 推送分支：`git push origin feature/amazing-feature`
5. 创建 Pull Request

### 代码规范

- 遵循 PEP 8 代码风格
- 新增功能请更新对应文档
- `.env` 文件包含敏感信息，**切勿提交**
- 提交前确保 `python -m py_compile` 通过语法检查

---

## 📄 许可证

本项目基于上游仓库 [charyelo-air/aiops](https://gitee.com/charyelo-air/aiops) 进行二次开发。

上游仓库未声明开源许可证。本仓库的增量代码（主要为 `monitoring/` 模块及相关增强部分）采用 MIT License。

---

## 🙏 致谢

- **[上游项目](https://gitee.com/charyelo-air/aiops)** — 提供了优秀的 CMDB / K8s / WebSSH / AI 对话基础框架
- **[Django](https://www.djangoproject.com/)** — Web 框架
- **[Django Channels](https://channels.readthedocs.io/)** — WebSocket 支持
- **[阿里云通义千问 Qwen](https://dashscope.console.aliyun.com/)** — AI 根因分析引擎
- **[OpenAI](https://openai.com/)** — 兼容 API 标准

---

<p align="center">
  <strong>🌟 感谢使用 AiOps 智能运维平台！</strong>
</p>
