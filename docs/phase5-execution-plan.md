# AiOps 实时预警与监控 — Phase 5 数据管道与高级运维执行计划

**文档版本**: v1.0-EXEC
**创建日期**: 2026-04-13
**基于**: `realtime-alerting-monitoring-analysis-and-implementation.md` §15 分阶段实施路线图
**前置条件**: Phase 1 + Phase 2 + Phase 3 + Phase 4 全部完成
**目标**: 实现数据采集 Agent 接口、告警路由/升级、依赖拓扑追踪、自定义仪表盘、巡检评分系统

---

## 📋 Phase 5 范围定义

### 本阶段交付物

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | **数据采集 Agent 接口 + Push API** | 服务器 Agent 主动推送指标到平台，支持批量写入、认证鉴权 |
| 2 | **告警升级/路由策略引擎** | 基于时间、严重级、次数的自动升级策略；按团队/角色路由 |
| 3 | **系统依赖拓扑图 + 健康链路追踪** | 服务间依赖关系建模；端到端健康状态可视化 |
| 4 | **自定义仪表盘保存与分享** | 用户可保存/加载/分享自定义 Dashboard 配置 |
| 5 | **定时巡检报告 & 健康评分系统** | 自动生成每日巡检报告；多维度服务器健康评分 |

### 不在本阶段范围

- Grafana/Prometheus 原生集成 (独立项目)
- Vue3 前端重构
- 多租户权限体系 (Phase 6)

---

## 🏗️ 架构设计

```
┌──────────────────────────────────────────────────────┐
│                   Phase 5 新增组件                    │
├──────────┬──────────┬──────────┬──────────┬─────────┤
│ Agent    │ Escalation│ Topology │ Dashboard│ Health  │
│ Push API │ Router    │ Tracker  │ Saver    │ Scorer  │
│ 数据推送  │ 升级路由  │ 拓扑追踪  │ 仪表盘   │ 巡检评分 │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬───┘
     │          │          │          │          │
     ▼          ▼          ▼          ▼          ▼
 ┌──────────────────────────────────────────────────┐
│              Phase 1~4 已有基础层                    │
│  RuleEngine / Aggregation / Correlation / Remediation│
│  WebSocket / Runbook / API / Celery                │
 └──────────────────────────────────────────────────┘
```

---

## 📡 Step 1: 数据采集 Agent 接口 + Push API

### 1.1 Agent 认证模型

```python
# monitoring/models.py 新增

class AgentToken(models.Model):
    name = models.CharField(max_length=200, verbose_name='Agent 名称')
    token = models.CharField(max_length=64, unique=True, db_index=True,
        verbose_name='API Token')
    server = models.OneToOneField('cmdb.Server', on_delete=models.CASCADE,
        related_name='agent_token', null=True, blank=True)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Agent Token'
```

### 1.2 Push API 端点

```
POST /api/monitoring/agent/push/
Headers: Authorization: Bearer <token>
Body: {
  "hostname": "web-01",
  "metrics": [
    {"metric": "cpu_usage", "value": 78.5, "timestamp": "..."},
    {"metric": "mem_usage", "value": 82.1},
    ...
  ],
  "tags": {"env": "prod", "region": "cn-east"}
}
Response: {"code":0,"accepted":5,"errors":[]}
```

特性：
- Token 认证 + IP 白名单（可选）
- 批量写入，单次最多 100 条
- 自动关联 Server 对象
- 更新 `last_seen_at` 用于存活检测
- 写入 `ServerMetric` 表复用已有结构

### 1.3 存活检测

Celery 定时任务检查 `last_seen_at` 超过 5 分钟未上报的 Agent → 触发 absence 类型告警。

---

## 🔔 Step 2: 告警升级/路由策略引擎

### 2.1 策略模型

```python
# monitoring/models.py 新增

class EscalationPolicy(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    match_rules = models.JSONField(default=dict, verbose_name='匹配规则')
    escalation_steps = models.JSONField(default=list, verbose_name='升级步骤')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = '升级策略'
```

`escalation_steps` 格式示例：
```json
[
  {"delay_minutes": 0, "action": "notify", "target": ["oncall_team"], "channel": ["dingtalk"]},
  {"delay_minutes": 15, "action": "notify", "target": ["team_lead"], "channel": ["dingtalk", "wechat"]},
  {"delay_minutes": 60, "action": "escalate_severity", "new_severity": "P0"},
  {"delay_minutes": 120, "action": "notify", "target": ["manager"], "channel": ["email"]}
]
```

### 2.2 升级引擎

文件: `monitoring/escalation/escalator.py`

逻辑：
1. 告警触发时查找匹配的 `EscalationPolicy`
2. 按 `escalation_steps` 的 `delay_minutes` 排队调度 Celery 任务
3. 到时间后执行对应 action（通知/升级级别）
4. 若告警在步骤执行前 resolved → 取消后续步骤
5. 支持暂停/恢复升级流程

---

## 🕸️ Step 3: 系统依赖拓扑图 + 健康链路追踪

### 3.1 拓扑模型

```python
# monitoring/models.py 新增

class ServiceTopology(models.Model):
    name = models.CharField(max_length=200, verbose_name='服务名')
    service_type = models.CharField(max_length=50, default='application',
        choices=[('application','应用服务'),('database','数据库'),
                 ('cache','缓存'),('queue','消息队列'),('lb','负载均衡'),
                 ('storage','存储'),('external','外部服务')])
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True, blank=True)
    health_endpoint = models.URLField(blank=True, verbose_name='健康检查URL')
    depends_on = models.ManyToManyField('self', symmetrical=False, blank=True,
        related_name='dependents', verbose_name='依赖的服务')

    class Meta:
        verbose_name = '服务拓扑节点'
```

### 3.2 链路健康追踪

文件: `monitoring/topology/tracker.py`

功能：
- 从根节点 DFS/BFS 遍历整条依赖链
- 每个节点的健康状态聚合：全部 OK → 绿色；部分异常 → 黄色；关键路径断 → 红色
- 影响面分析：某节点故障 → 受影响的上游服务列表
- API 返回拓扑 JSON 用于前端 D3.js 力导向图渲染

### 3.3 API

```
GET  /api/monitoring/topology/nodes/           — 所有拓扑节点
GET  /api/monitoring/topology/graph/           — 完整依赖图(JSON)
GET  /api/monitoring/topology/impact/<node_id>/— 故障影响分析
POST /api/monitoring/topology/nodes/           — 创建节点+关系
```

---

## 📊 Step 4: 自定义仪表盘保存与分享

### 4.1 模型

```python
# monitoring/models.py 新增

class SavedDashboard(models.Model):
    name = models.CharField(max_length=200)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    config = models.JSONField(verbose_name='面板配置(图表类型/指标/布局)')
    is_public = models.BooleanField(default=False, verbose_name='是否公开')
    share_token = models.CharField(max_length=32, unique=True, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = '已保存的仪表盘'
```

### 4.2 API

```
GET    /api/monitoring/dashboards/saved/         — 我的仪表盘列表
POST   /api/monitoring/dashboards/saved/         — 保存当前配置
GET    /api/monitoring/dashboards/saved/<id>/    — 加载配置
PUT    /api/monitoring/dashboards/saved/<id>/    — 更新配置
DELETE /api/monitoring/dashboards/saved/<id>/    — 删除
POST   /api/monitoring/dashboards/<id>/share/   — 生成/撤销分享链接
```

---

## 🏥 Step 5: 定时巡检报告 & 健康评分系统

### 5.1 健康评分模型

```python
# monitoring/models.py 新增

class HealthScore(models.Model):
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, related_name='health_scores')
    scored_at = models.DateTimeField(db_index=True)
    overall_score = models.FloatField(verbose_name='综合评分(0-100)')

    cpu_score = models.FloatField(default=100)
    mem_score = models.FloatField(default=100)
    disk_score = models.FloatField(default=100)
    network_score = models.FloatField(default=100)
    availability_score = models.FloatField(default=100)

    alert_penalty = models.FloatField(default=0, verbose_name='告警扣分')
    anomaly_penalty = models.FloatField(default=0, verbose_name='异常扣分')

    grade = models.CharField(max_length=10, default='A',
        choices=[('A','优秀(A)'),('B','良好(B)'),('C','一般(C)'),
                 ('D','警告(D)'),('F','严重(F)')])

    class Meta:
        ordering = ['-scored_at']
        verbose_name = '健康评分'
```

### 5.2 评分引擎

文件: `monitoring/health/scorer.py`

算法：
- **CPU**: score = max(0, 100 - max(0, avg_cpu - 60) * 2 - max(0, avg_cpu - 85) * 4)
- **内存**: 同理，阈值 75/90
- **磁盘**: 阈值 80/95
- **可用性**: 基于 uptime% 映射
- **告警扣分**: 每条 firing 告警 -3 分，P0/P1 双倍
- **异常扣分**: 每条 high 异常 -5 分
- **综合**: 加权平均 CPU*0.25 + MEM*0.25 + DISK*0.20 + NET*0.15 + AVAIL*0.15 - penalties
- **等级**: A(≥90) B(≥75) C(≥60) D(≥40) F(<40)

### 5.3 巡检任务

Celery Beat 每天早上 8 点执行：
1. 对所有 Running 服务器计算最新 HealthScore
2. 生成巡检摘要（Top 问题服务器、趋势变化、SLA 达标情况）
3. 通过通知渠道发送给运维团队
4. 将结果存入数据库供前端展示

### 5.4 API

```
GET /api/monitoring/health/scores/?server_id=&days=7     — 历史评分曲线
GET /api/monitoring/health/ranking/                      — 健康排行榜
GET /api/monitoring/health/report/latest/                — 最新巡检报告
POST /api/monitoring/health/scan/now/                    — 手动触发巡检
```

---

## 📁 文件变更清单

### 新建文件

| 文件 | 用途 |
|------|------|
| `monitoring/agent/__init__.py` | 包初始化 |
| `monitoring/agent/push_api.py` | Agent Push API 处理 |
| `monitoring/escalation/__init__.py` | 包初始化 |
| `monitoring/escalation/escalator.py` | 升级路由引擎 |
| `monitoring/topology/__init__.py` | 包初始化 |
| `monitoring/topology/tracker.py` | 拓扑追踪与健康链路 |
| `monitoring/health/__init__.py` | 包初始化 |
| `monitoring/health/scorer.py` | 健康评分引擎 |

### 修改文件

| 文件 | 变更内容 |
|------|----------|
| `monitoring/models.py` | 新增 AgentToken/EscalationPolicy/ServiceTopology/SavedDashboard/HealthScore |
| `monitoring/admin.py` | 注册所有新模型 |
| `monitoring/api/views.py` | 新增 agent/push/topology/dashboard/health 视图 |
| `monitoring/api/urls.py` | 新增路由 |
| `templates/index.html` | 新增健康评分卡片和拓扑入口 |

---

## ✅ 验收标准

1. **Agent Push**: 可通过 POST 推送指标数据，Token 认证正常工作
2. **升级策略**: P1 告警 15 分钟未确认自动升级通知给 Team Lead
3. **拓扑图**: 前端展示服务依赖力导向图，故障节点高亮
4. **仪表盘保存**: 用户可保存/加载/分享自定义面板配置
5. **健康评分**: 每台服务器显示 A~F 等级评分，支持历史曲线
6. **巡检报告**: 每天 8 点自动发送巡检摘要邮件
