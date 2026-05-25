# AiOps 智能运维平台 — 全面架构分析与拓展规划报告

**报告版本**: v1.0
**分析日期**: 2026-05-25
**项目定位**: 面向中小企业运维智能化，降低运维监控体系使用成本，支持本地+云混合监控

---

## 一、项目概览

### 1.1 项目简介

AiOps 智能运维平台基于 [Gitee 上游仓库](https://gitee.com/charyelo-air/aiops) 二次开发，在继承 CMDB/WebSSH/K8s 管理/AI 对话等基础能力之上，**全新构建了完整的 AIOps 监控告警体系**，实现了从「被动运维」到「AI 驱动的智能辅助」的跨越。

### 1.2 项目核心价值主张

| 维度 | 描述 |
|------|------|
| **目标用户** | 中小企业运维团队（5-50人规模） |
| **核心痛点** | 商业运维平台成本高、开源方案部署复杂、缺乏AI智能分析 |
| **差异化** | 开箱即用的 AIOps 能力 + 低部署成本 + 本地/云混合监控 |

---

## 二、核心功能模块分析

### 2.1 功能模块全景图

```
┌─────────────────────────────────────────────────────────────────────┐
│                      AiOps 智能运维平台                              │
├────────────┬────────────┬────────────┬────────────┬────────────────┤
│  system    │   cmdb     │ monitoring │k8s_manager │script_manager  │
│  系统管理   │  资产管理   │ 智能监控    │ K8s容器管理 │ 脚本管理       │
│            │            │            │            │                │
│ ·用户管理   │ ·服务器资产  │ ·告警规则   │ ·多集群管理 │ ·脚本库        │
│ ·角色权限   │ ·WebSSH    │ ·异常检测   │ ·Pod/Deploy│ ·批量执行      │
│ ·LDAP认证   │ ·审计日志   │ ·AI根因分析 │ ·容器终端   │ ·历史版本      │
│ ·系统配置   │ ·Agent采集  │ ·告警关联   │ ·YAML审计   │ ·AI代码优化    │
│ ·密码策略   │ ·云同步     │ ·自动修复   │ ·Helm商店   │               │
│            │ ·SSL证书    │ ·知识库     │ ·资源CRUD   │               │
│            │ ·高危审计   │ ·健康评分   │            │               │
│            │ ·Java诊断   │ ·拓扑追踪   │            │               │
│            │ ·SFTP传输   │ ·仪表盘保存 │            │               │
├────────────┴────────────┴────────────┴────────────┴────────────────┤
│                       ai_ops · AI对话平台                            │
│  ·多模型管理 (Qwen/DeepSeek/GPT)  ·对话会话  ·流式响应              │
├─────────────────────────────────────────────────────────────────────┤
│                       agent · K8s Node 采集器                        │
│  ·Node指标上报  ·组件日志抓取  ·K8s API代理                         │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 各模块功能清单

#### 模块一：system — 系统管理

| 功能 | 状态 | 说明 |
|------|------|------|
| 用户管理 | ✅ 完整 | CRUD + 状态切换 + 密码重置 |
| 角色权限 (RBAC) | ✅ 完整 | 角色→服务器分组，数据级权限控制 |
| LDAP 认证 | ✅ 可用 | 自定义 LDAPBackend + 数据库认证保底 |
| 密码策略 | ✅ 完整 | 复杂度验证 + 最小长度 + 弱密码检测 |
| 系统配置 | ✅ 基础 | Key-Value 配置表，用于通知渠道等 |

#### 模块二：cmdb — 资产管理

| 功能 | 状态 | 说明 |
|------|------|------|
| 服务器 CRUD | ✅ 完整 | 含分组、硬件配置、导入导出 |
| WebSSH | ✅ 完整 | xterm.js + WebSocket + SFTP + 操作录像 |
| Agent 采集 | ✅ 完整 | Agentless SSH + Agent Push 双模式 |
| 云同步 | ✅ 可用 | 阿里云/腾讯云 ECS 实例同步 |
| SSL 证书管理 | ✅ 完整 | 自动发现 + 到期提醒 + Celery 定时检查 |
| 高危审计 | ✅ 完整 | 危险命令拦截 + AI 评估建议 |
| Java 诊断 | ✅ 可用 | jstack 在线线程堆栈分析 |
| SFTP 文件传输 | ✅ 完整 | 上传/下载/文件操作 |

#### 模块三：monitoring — 智能监控（核心增强）

| 功能 | 状态 | Phase | 说明 |
|------|------|-------|------|
| 告警规则引擎 | ✅ 完整 | P1 | 6种规则类型 + 冷却/静默/频率限制 |
| 异常检测算法 | ✅ 完整 | P1 | ZScore/IQR/MovingAvg/RateOfChange/Composite |
| 多渠道通知 | ✅ 完整 | P1 | 钉钉/企微/邮件/Slack/Webhook + 重试 |
| REST API | ✅ 完整 | P1 | 规则CRUD + 告警管理 + 统计 |
| 异常可视化标注 | ✅ 完整 | P2 | ECharts markPoint + 时间线 |
| AI 诊断联动 | ✅ 完整 | P2 | Qwen3 根因分析 + 置信度评分 |
| 检测参数调优 | ✅ 完整 | P2 | Admin 算法配置面板 |
| 历史异常回溯 | ✅ 完整 | P2 | 时间范围查询 + 指标曲线 |
| WebSocket 推送 | ✅ 完整 | P3 | 实时指标/告警广播 |
| TopN 排行 | ✅ 完整 | P3 | CPU/内存/磁盘 Top10 |
| 时间范围选择 | ✅ 完整 | P3 | 1h/6h/24h/7d/30d 聚合 |
| PDF 报告导出 | ✅ 完整 | P3 | weasyprint 生成 |
| 告警聚合去重 | ✅ 完整 | P4 | AlertGroup + 指纹聚合 |
| 告警关联分析 | ✅ 完整 | P4 | Correlator + 因果关系推理 |
| 自动修复引擎 | ✅ 完整 | P4 | 脚本/重启/清理/扩容 + 危险确认 |
| 运维知识库 | ✅ 完整 | P4 | RunbookEntry + 智能推荐 + 反馈评分 |
| 统计大屏 API | ✅ 完整 | P4 | MTTA/MTTR/SLA/趋势 |
| Agent Push API | ✅ 完整 | P5 | Token 认证 + 批量写入 + 存活检测 |
| 告警升级策略 | ✅ 完整 | P5 | EscalationPolicy + 时间/级别/次数升级 |
| 服务拓扑追踪 | ✅ 完整 | P5 | ServiceTopology + 影响分析 |
| 自定义仪表盘 | ✅ 完整 | P5 | 保存/加载/分享 Dashboard |
| 健康评分系统 | ✅ 完整 | P5 | 多维度评分 + A~F 等级 + 巡检报告 |
| 告警评论 | ✅ 完整 | P4 | 多类型评论 + 关闭原因 + 内部备注 |

#### 模块四：k8s_manager — K8s 容器管理

| 功能 | 状态 | 说明 |
|------|------|------|
| 多集群管理 | ✅ 完整 | KubeConfig 导入 + Token 认证 |
| 全资源覆盖 | ✅ 完整 | Pod/Deploy/StatefulSet/DaemonSet/Service/Ingress/ConfigMap/Secret/PV/PVC/StorageClass |
| 容器终端 | ✅ 完整 | WebSocket + 实时日志 |
| YAML 智能审计 | ✅ 可用 | AI 安全检查 |
| Helm 商店 | ✅ 可用 | Chart 管理 |
| 节点快照 | ✅ 完整 | Agent 上报 Node 指标 + 组件日志 |

#### 模块五：script_manager — 脚本管理

| 功能 | 状态 | 说明 |
|------|------|------|
| 脚本库 | ✅ 完整 | Shell/Python/Ansible + 版本控制 |
| 批量执行 | ✅ 完整 | 并发控制 + 超时 + 单机日志 |
| AI 代码优化 | ✅ 可用 | 通过 AI 对话模块辅助 |

#### 模块六：ai_ops — AI 对话平台

| 功能 | 状态 | 说明 |
|------|------|------|
| 多模型管理 | ✅ 完整 | OpenAI 兼容接口，支持 Qwen/DeepSeek/GPT |
| 对话会话 | ✅ 完整 | 会话管理 + 消息历史 |
| 流式响应 | ✅ 可用 | SSE 流式输出 |

### 2.3 模块间交互关系

```
                    ┌──────────────┐
                    │   用户/浏览器  │
                    └──────┬───────┘
                           │ HTTP / WebSocket
                    ┌──────▼───────┐
                    │  Django URL   │
                    │  Router       │
                    └──┬───┬───┬───┘
                       │   │   │
          ┌────────────┘   │   └────────────┐
          ▼                ▼                ▼
   ┌──────────┐   ┌──────────────┐   ┌───────────┐
   │  system  │   │  monitoring  │   │  cmdb     │
   │  用户认证  │   │  告警/检测    │   │  资产/SSH  │
   └────┬─────┘   └──┬───┬───┬──┘   └─────┬─────┘
        │            │   │   │             │
        │            │   │   │  ┌──────────┘
        │            │   │   │  │ ServerMetric
        │            │   │   │  │ (共享数据)
        │            │   │   │  │
        │      ┌─────┘   │   └──┼──► RuleEvaluator ──► AlertEvent
        │      │         │      │
        │      ▼         ▼      ▼
        │  AnomalyDetector  AI Callback   Correlator
        │      │         │              │
        │      ▼         ▼              ▼
        │  AnomalyHistory  Qwen3 API   AlertGroup
        │                   │
        │                   ▼
        │           RemediationEngine
        │                   │
        │                   ▼
        │           RunbookRecommender
        │
        └────► RBAC 权限校验 (ServerGroupAuth)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
  k8s_manager  script_manager  ai_ops
  (K8s API)    (Paramiko)     (OpenAI SDK)
        │           │           │
        ▼           ▼           ▼
  Kubernetes    SSH 执行     LLM API
  Python Client              (Qwen/GPT)
```

**核心数据流**：

1. **指标采集流**: Server → (SSH/Agent) → ServerMetric → RuleEvaluator → AlertEvent
2. **告警处理流**: AlertEvent → (通知/关联/升级) → NotificationLog / AlertGroup / EscalationPolicy
3. **AI 诊断流**: AlertEvent → Celery Task → Qwen3 API → AnomalyHistory.ai_diagnosis
4. **自愈修复流**: AlertEvent → RemediationEngine → subprocess → RemediationHistory
5. **实时推送流**: Celery Beat → broadcast_metrics → WebSocket → Dashboard

---

## 三、技术架构体系

### 3.1 技术栈全景

| 类别 | 技术选型 | 版本 | 用途 |
|------|----------|------|------|
| **后端框架** | Django | 4.x+ | Web 框架 + ORM + Admin |
| **异步通信** | Django Channels | 3.0.4 | WebSocket 双向通信 |
| **ASGI 服务器** | Daphne | 3.x | 生产级 ASGI 服务 |
| **任务队列** | Celery | 5.6.0 | 异步任务 + 定时调度 |
| **Worker 模式** | eventlet | - | 协程并发 |
| **消息代理** | Redis | - | Celery Broker + Channels Layer |
| **AI 引擎** | OpenAI Python SDK | 2.9.0 | 兼容 Qwen3/DeepSeek/GPT |
| **异常检测** | NumPy / SciPy / scikit-learn / statsmodels | - | 统计分析 + 机器学习 |
| **SSH 交互** | Paramiko | - | 远程命令 + SFTP |
| **K8s 交互** | Kubernetes Python Client | 34.1.0 | 集群管理 API |
| **数据库** | SQLite (开发) / PostgreSQL 18 (生产) | - | 双模式支持 |
| **字段加密** | django-fernet-fields-v2 | 0.9 | SSH密码/SecretKey 加密 |
| **定时调度** | APScheduler | 3.11.1 | 规则评估调度 |
| **云 SDK** | aliyun-python-sdk-ecs / tencentcloud-sdk-python | - | 云实例同步 |
| **前端** | Django Templates + Bootstrap 4 + ECharts 5 + Xterm.js + Ace Editor | - | 服务端渲染 |
| **PDF 导出** | weasyprint | - | 报告生成 |
| **静态文件** | WhiteNoise | - | 生产环境静态文件服务 |
| **环境管理** | python-dotenv | 1.0+ | .env 配置加载 |

### 3.2 架构分层图

```
┌─────────────────────────────────────────────────────────────┐
│                      前端展示层                               │
│  Django Templates · Bootstrap 4 · ECharts 5 · Xterm.js      │
│  Ace Editor · WebSocket Client · PDF Viewer                  │
├─────────────────────────────────────────────────────────────┤
│                      API 网关层                               │
│  Django URL Router · CSRF · Auth · LoginRequired             │
│  /api/monitoring/* · /k8s/* · /script/* · /ai/*             │
├─────────────────────────────────────────────────────────────┤
│                      业务逻辑层                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │RuleEngine│ │Anomaly   │ │Correlator│ │Remediation│       │
│  │规则引擎   │ │Detector  │ │关联分析   │ │Engine    │       │
│  │          │ │异常检测   │ │          │ │自愈修复   │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │Notificat-│ │Health    │ │Runbook   │ │Escalation│       │
│  │ionRouter │ │Scorer    │ │Recommender│ │Escalator │       │
│  │通知路由   │ │健康评分   │ │知识推荐   │ │升级策略   │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│                      异步任务层                               │
│  Celery Worker (eventlet) · Celery Beat · APScheduler        │
│  broadcast_metrics · anomaly_ai_callback · send_alert_notify │
│  execute_remediation · daily_health_scan · agent_liveness    │
├─────────────────────────────────────────────────────────────┤
│                      数据持久层                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ PostgreSQL   │  │    Redis     │  │   SQLite     │      │
│  │ (生产模式)    │  │  Broker+Cache│  │  (开发模式)   │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
├─────────────────────────────────────────────────────────────┤
│                      基础设施层                               │
│  Daphne ASGI · Nginx (反代) · Docker (Agent) · SSH          │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 数据库设计

#### 核心数据模型关系

```
User (system) ──1:N──► AlertEvent.acknowledged_by
                         AlertEvent.resolved_by
                         AlertRule.created_by
                         AlertComment.author

ServerGroup ──1:N──► Server.group
                M:N──► Group (角色) [via ServerGroupAuth]

Server (cmdb) ──1:N──► ServerMetric
                  1:N──► AlertEvent
                  1:N──► AnomalyHistory
                  1:N──► HealthScore
                  1:1──► AgentToken
                  1:N──► TerminalLog
                  1:N──► ServiceTopology

AlertRule ──1:N──► AlertEvent
              1:N──► AlertSilenceRule

AlertEvent ──1:N──► NotificationLog
             1:N──► AlertComment
             1:N──► RemediationHistory
             1:1──► AnomalyHistory

AlertGroup ──聚合──► AlertEvent (via fingerprint)

ServiceTopology ──M:N──► self (depends_on)
```

#### 数据量表估算

| 模型 | 预估增长 (100台服务器) | 存储压力 |
|------|----------------------|----------|
| ServerMetric | ~14.4万条/天 (100×6指标×240采样) | ⚠️ 高 |
| AlertEvent | ~10-50条/天 | 低 |
| AnomalyHistory | ~5-20条/天 | 低 |
| HealthScore | ~100条/天 | 低 |
| NotificationLog | ~30-100条/天 | 低 |
| TerminalLog | ~10-50条/天 | 中 (含录像文件) |

### 3.4 中间件选型

| 中间件 | 角色 | 选型理由 |
|--------|------|----------|
| Redis | Celery Broker + Channels Layer | 高性能、低延迟、支持 Pub/Sub |
| Celery | 异步任务队列 | Django 生态首选、支持定时/重试/链式任务 |
| Daphne | ASGI 服务器 | Channels 官方推荐、支持 HTTP + WebSocket |
| WhiteNoise | 静态文件服务 | 零依赖、适合中小规模部署 |

---

## 四、性能指标与可扩展性评估

### 4.1 性能评估

| 指标 | 当前状态 | 评估 |
|------|----------|------|
| **指标采集延迟** | Agent: ~5s / SSH: ~30s | ✅ 满足准实时需求 |
| **规则评估频率** | 60s 间隔 | ✅ 适合中小企业规模 |
| **WebSocket 推送** | 30s 广播间隔 | ⚠️ 可优化至 5-10s |
| **AI 诊断响应** | 3-8s (Qwen3 API) | ✅ 可接受 |
| **告警通知延迟** | <10s (钉钉/企微) | ✅ 满足需求 |
| **API 响应时间** | 50-200ms (常规查询) | ✅ 良好 |
| **并发连接** | ~100 WebSocket | ⚠️ 单 Daphne 实例限制 |

### 4.2 可扩展性评估

| 维度 | 当前能力 | 扩展瓶颈 | 评分 |
|------|----------|----------|------|
| **服务器规模** | 100-500台 | ServerMetric 全量查询无分表 | ⭐⭐⭐ |
| **规则数量** | 50-200条 | 规则评估串行执行 | ⭐⭐⭐ |
| **WebSocket 并发** | ~100连接 | 单 Daphne + 单 Redis | ⭐⭐ |
| **AI 诊断吞吐** | ~10次/分钟 | 受 LLM API 限流 | ⭐⭐⭐ |
| **数据库写入** | ~1000条/分钟 | SQLite 不支持并发写 | ⭐⭐ |
| **水平扩展** | 不支持 | 无状态分离不彻底 | ⭐⭐ |

### 4.3 潜在技术债务

#### 🔴 高优先级

| 编号 | 技术债务 | 影响 | 修复建议 |
|------|----------|------|----------|
| TD-1 | **ServerMetric 无数据保留策略** | 数据库无限增长，查询变慢 | 实现数据保留策略（如保留30天明细 + 聚合历史） |
| TD-2 | **SQLite 生产环境不可用** | 并发写入锁、无复制、性能瓶颈 | 强制生产环境使用 PostgreSQL |
| TD-3 | **规则评估串行执行** | 规则数量多时评估延迟增大 | 改为 Celery 并行评估或异步分片 |
| TD-4 | **API 无分页优化** | `api_rules` 全量加载无分页 | 添加 Django Paginator |
| TD-5 | **RemediationEngine 使用 subprocess** | 命令注入风险、无沙箱 | 改用 Paramiko 远程执行或容器化沙箱 |

#### 🟡 中优先级

| 编号 | 技术债务 | 影响 | 修复建议 |
|------|----------|------|----------|
| TD-6 | **前端无 SPA 框架** | 交互体验差、全页刷新 | 逐步引入 Vue3/React 组件化 |
| TD-7 | **无 API 认证体系** | 仅 Session Auth，无 Token/API Key | 引入 DRF + JWT / API Key 认证 |
| TD-8 | **通知渠道配置硬编码** | SystemConfig KV 存储，无校验 | 增加通知渠道配置 UI + 校验 |
| TD-9 | **异常检测纯内存计算** | 每次从 DB 加载历史数据 | 引入 Redis 缓存时序窗口 |
| TD-10 | **Agent 无加密通信** | Push API 仅 Token 认证 | 增加 TLS + 签名校验 |
| TD-11 | **无多租户隔离** | 所有用户共享数据 | 添加 Tenant 模型 + 数据过滤 |

#### 🟢 低优先级

| 编号 | 技术债务 | 影响 | 修复建议 |
|------|----------|------|----------|
| TD-12 | **测试覆盖率低** | models.py tests.py 为空 | 补充单元测试 + 集成测试 |
| TD-13 | **日志无结构化** | 纯文本日志，难以检索 | 引入 structlog / JSON 日志 |
| TD-14 | **无 CI/CD 流水线** | 手动部署、无自动化测试 | 添加 GitHub Actions / GitLab CI |
| TD-15 | **Fernet Key 硬编码** | settings.py 中有默认 Key | 强制从 .env 读取 |
| TD-16 | **Celery Beat 与 APScheduler 并存** | 调度逻辑分散 | 统一使用 Celery Beat |

---

## 五、3-6 个月功能拓展规划

### 5.1 拓展路线图

```
Month 1-2                    Month 3-4                    Month 5-6
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  Phase 6:        │    │  Phase 7:        │    │  Phase 8:        │
│  云平台集成 &     │    │  平台化 &        │    │  AI深化 &        │
│  数据管道优化     │    │  前端现代化       │    │  生态扩展        │
│                  │    │                  │    │                  │
│ ·多云数据接入    │    │ ·DRF + JWT API   │    │ ·预测性运维      │
│ ·混合监控仪表盘  │    │ ·Vue3 前端重构   │    │ ·容量规划        │
│ ·数据保留策略    │    │ ·多租户基础      │    │ ·日志分析引擎    │
│ ·准实时告警优化  │    │ ·移动端适配      │    │ ·链路追踪集成    │
│ ·Agent 安全加固  │    │ ·插件系统设计    │    │ ·开放 API 生态   │
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

### 5.2 Phase 6: 云平台集成与数据管道优化（Month 1-2）

> **目标**: 实现本地+云混合监控，解决中小企业多云环境下的统一运维需求

#### 6.1 多云平台数据接入

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 阿里云 CloudMonitor 集成 | 通过 API 拉取 ECS/RDS/SLB/OSS 指标 | P0 |
| 腾讯云 CloudMonitor 集成 | 通过 API 拉取 CVM/MySQL/CLB/COS 指标 | P0 |
| 华为云 CloudEye 集成 | 通过 API 拉取 ECS/RDS/ELB 指标 | P1 |
| AWS CloudWatch 集成 | EC2/RDS/ELB 指标（可选） | P2 |
| 云事件订阅 | 通过 MNS/SQS 接收云平台事件告警 | P1 |

**架构设计**:

```
┌──────────────────────────────────────────────────────────┐
│                  Cloud Data Adapter Layer                  │
├──────────┬──────────┬──────────┬──────────┬──────────────┤
│ Aliyun   │ Tencent  │ Huawei   │  AWS     │  Custom      │
│ Adapter  │ Adapter  │ Adapter  │ Adapter  │  Webhook     │
│          │          │          │          │  Receiver     │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴──────┬───────┘
     │          │          │          │            │
     ▼          ▼          ▼          ▼            ▼
┌──────────────────────────────────────────────────────────┐
│              Unified Metric Normalizer                     │
│  cloud_provider · resource_type · metric → ServerMetric   │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
              ┌─────────────────────┐
              │   RuleEvaluator     │
              │   (统一告警评估)      │
              └─────────────────────┘
```

**关键设计**: 新增 `CloudResource` 模型，将云资源映射到统一的 `ServerMetric` 结构，实现本地+云指标统一评估。

```python
class CloudResource(models.Model):
    PROVIDER_CHOICES = [
        ('aliyun', '阿里云'), ('tencent', '腾讯云'),
        ('huawei', '华为云'), ('aws', 'AWS'),
    ]
    RESOURCE_TYPE_CHOICES = [
        ('ecs', '云服务器'), ('rds', '云数据库'),
        ('slb', '负载均衡'), ('oss', '对象存储'),
        ('redis', '云缓存'), ('cdn', 'CDN'),
    ]
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    resource_type = models.CharField(max_length=20, choices=RESOURCE_TYPE_CHOICES)
    instance_id = models.CharField(max_length=100)
    instance_name = models.CharField(max_length=200)
    region = models.CharField(max_length=50)
    cloud_account = models.ForeignKey('cmdb.CloudAccount', on_delete=models.CASCADE)
    local_server = models.ForeignKey('cmdb.Server', null=True, blank=True, on_delete=models.SET_NULL)
    extra_config = models.JSONField(default=dict)
    last_sync_at = models.DateTimeField(null=True)
```

#### 6.2 混合监控仪表盘

- 本地服务器 + 云资源统一视图
- 按云厂商/区域/资源类型分组
- 云资源成本概览（月度费用趋势）
- 跨云资源关联告警

#### 6.3 数据保留策略

```python
# 新增数据保留配置
class DataRetentionPolicy(models.Model):
    metric_type = models.CharField(max_length=50)  # raw / aggregated
    retention_days = models.IntegerField(default=30)
    aggregation_interval = models.CharField(max_length=20, default='1h')  # 5m/1h/1d
```

- 原始指标保留 7-30 天
- 5分钟聚合保留 90 天
- 1小时聚合保留 1 年
- Celery Beat 定时执行数据清理

#### 6.4 准实时告警优化

- WebSocket 推送间隔从 30s 降至 5s
- 引入 Redis Pub/Sub 实现指标变更即时通知
- Agent Push API 支持增量推送（仅推送变化指标）
- 规则评估支持事件驱动模式（新指标到达时立即评估关联规则）

#### 6.5 Agent 安全加固

- TLS 加密通信
- 请求签名校验（HMAC-SHA256）
- IP 白名单 + Token 双重认证
- Agent 心跳超时自动降级为 SSH 采集

### 5.3 Phase 7: 平台化与前端现代化（Month 3-4）

> **目标**: 提升平台可扩展性和用户体验，为企业级部署做准备

#### 7.1 Django REST Framework + JWT 认证

- 引入 DRF 替代手写 API View
- JWT Token 认证 + Refresh Token
- API 版本管理 (`/api/v1/`, `/api/v2/`)
- API 限流 (throttling)
- OpenAPI Schema 自动生成

#### 7.2 Vue3 前端渐进式重构

**策略**: 不做一次性重写，采用微前端/组件替换方式

| 阶段 | 模块 | 技术方案 |
|------|------|----------|
| 第一批 | 监控 Dashboard | Vue3 + ECharts 组件 |
| 第二批 | 告警管理页面 | Vue3 + Ant Design Vue |
| 第三批 | CMDB 资产管理 | Vue3 + ProTable |
| 第四批 | K8s 管理页面 | Vue3 + Xterm.js |
| 第五批 | 系统设置 | Vue3 + Form |

#### 7.3 多租户基础

```python
class Tenant(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    plan = models.CharField(max_length=20, default='free')  # free/pro/enterprise
    max_servers = models.IntegerField(default=50)
    max_rules = models.IntegerField(default=20)
    settings = models.JSONField(default=dict)

# 所有核心模型添加 tenant_id 字段
# Middleware 自动注入租户过滤
```

#### 7.4 移动端适配

- 响应式布局优化
- 钉钉/企微小程序嵌入
- 告警推送移动端卡片
- 简化版移动 Dashboard

#### 7.5 插件系统设计

```python
class Plugin(models.Model):
    name = models.CharField(max_length=100)
    plugin_type = models.CharField(max_length=20)  # collector/notifier/analyzer/reporter
    version = models.CharField(max_length=20)
    config_schema = models.JSONField()  # JSON Schema
    is_enabled = models.BooleanField(default=False)
    entry_point = models.CharField(max_length=200)  # Python import path
```

- Collector 插件: 自定义指标采集器
- Notifier 插件: 自定义通知渠道
- Analyzer 插件: 自定义异常检测算法
- Reporter 插件: 自定义报表模板

### 5.4 Phase 8: AI 深化与生态扩展（Month 5-6）

> **目标**: 深化 AIOps 智能能力，构建开放运维生态

#### 8.1 预测性运维

| 功能 | 说明 |
|------|------|
| 容量预测 | 基于历史趋势预测 CPU/内存/磁盘使用率，提前预警 |
| 告警预测 | 基于时间序列模式预测未来告警概率 |
| 故障预判 | 基于多维指标关联分析，预判潜在故障 |
| 智能基线 | 自动学习业务周期模式（日/周/月），生成动态基线 |

**技术方案**: 使用 statsmodels 的 ARIMA/Prophet 进行时间序列预测，结合 scikit-learn 的 Isolation Forest 进行多维异常检测。

#### 8.2 日志分析引擎

```
┌────────────────────────────────────────────────────────┐
│                   Log Analysis Pipeline                  │
├──────────┬──────────┬──────────┬──────────┬────────────┤
│  Log     │  Pattern │  Anomaly │  AI Log  │  Alert     │
│  Collector│ Miner   │  Detector│  Summarizer│ Generator │
│  日志采集  │ 模式挖掘  │ 异常检测  │ AI摘要    │ 告警生成   │
└──────────┴──────────┴──────────┴──────────┴────────────┘
```

- 支持采集: Syslog / 应用日志 / K8s Pod 日志 / 云日志服务
- 模式挖掘: 自动识别日志模式，减少日志噪声
- AI 摘要: LLM 自动总结日志异常段
- 日志告警: 关键字/模式匹配触发告警

#### 8.3 链路追踪集成

- OpenTelemetry SDK 接入
- 分布式追踪数据存储 (ClickHouse/Redis)
- 服务调用拓扑自动生成
- 慢接口/错误率关联告警

#### 8.4 开放 API 生态

- 完整的 REST API + WebSocket API 文档
- Webhook 出站（告警/事件/报告）
- Terraform Provider（基础设施即代码）
- Ansible Module（自动化运维集成）
- Grafana Data Source Plugin（可视化对接）

---

## 六、资源需求评估

### 6.1 人力资源

| 角色 | Phase 6 (M1-2) | Phase 7 (M3-4) | Phase 8 (M5-6) |
|------|-----------------|-----------------|-----------------|
| 后端工程师 (Python) | 2人 | 1人 | 2人 |
| 前端工程师 (Vue3) | 0.5人 | 2人 | 1人 |
| DevOps 工程师 | 1人 | 0.5人 | 0.5人 |
| AI/ML 工程师 | 0 | 0 | 1人 |
| 测试工程师 | 0.5人 | 0.5人 | 0.5人 |

### 6.2 基础设施

| 资源 | 当前 | Phase 6 | Phase 7 | Phase 8 |
|------|------|---------|---------|---------|
| 应用服务器 | 1台 (2C4G) | 2台 (4C8G) | 2台 (4C8G) | 3台 (4C8G) |
| PostgreSQL | 共用 | 独立 (4C8G) | 独立 (4C8G) | 独立 (8C16G) |
| Redis | 共用 | 独立 (2C4G) | 独立 (2C4G) | 集群 (3×2C4G) |
| 对象存储 | 无 | 50GB (日志/录像) | 100GB | 200GB |
| LLM API | Qwen3 | + Qwen3 长文本 | 不变 | + 本地模型 |

### 6.3 预算估算（月度）

| 项目 | Phase 6 | Phase 7 | Phase 8 |
|------|---------|---------|---------|
| 云服务器 | ¥2,000 | ¥2,000 | ¥3,500 |
| 数据库 (RDS) | ¥1,500 | ¥1,500 | ¥3,000 |
| LLM API | ¥500 | ¥500 | ¥1,500 |
| 域名/CDN | ¥200 | ¥200 | ¥200 |
| **月度合计** | **¥4,200** | **¥4,200** | **¥8,200** |

---

## 七、风险与缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 多云 API 变更/限流 | 中 | 高 | 适配器模式 + 请求限流 + 降级策略 |
| Vue3 重构周期过长 | 高 | 中 | 渐进式替换，Django Template + Vue3 共存 |
| LLM API 成本失控 | 中 | 中 | 缓存诊断结果 + 本地小模型降级 |
| 数据量增长导致性能下降 | 高 | 高 | 数据保留策略 + 时序聚合 + 分区表 |
| 安全漏洞 (命令注入等) | 中 | 高 | 沙箱执行 + 输入校验 + 安全审计 |

---

## 八、总结

### 8.1 项目现状总结

AiOps 智能运维平台已经构建了**完整的 AIOps 监控告警体系**（Phase 1-5），涵盖从数据采集、异常检测、AI 诊断、告警关联、自动修复到知识库推荐的全链路能力。技术架构以 Django + Celery + Redis + WebSocket 为核心，适合中小企业 100-500 台服务器规模的运维场景。

### 8.2 核心优势

1. **开箱即用的 AIOps 能力** — 6+ 异常检测算法 + Qwen3 AI 根因分析
2. **混合采集模式** — Agentless SSH + Agent Push，适应各种网络环境
3. **完整的告警生命周期** — 规则→检测→通知→关联→升级→修复→知识沉淀
4. **低部署成本** — SQLite 开发模式 + 单机部署即可运行

### 8.3 关键改进方向

1. **多云集成** — 中小企业最迫切的需求，本地+云统一监控
2. **数据管道优化** — 解决 ServerMetric 无限增长问题，实现准实时告警
3. **前端现代化** — 提升用户体验，降低学习成本
4. **平台化** — 多租户 + 插件系统 + 开放 API，支撑商业化

---

> **报告结束** — 本报告基于项目代码库完整分析，涵盖功能清单、架构图、技术栈说明及拓展路线图。
