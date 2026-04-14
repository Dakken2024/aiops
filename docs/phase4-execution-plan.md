# AiOps 实时预警与监控 — Phase 4 智能运维增强执行计划

**文档版本**: v1.0-EXEC
**创建日期**: 2026-04-13
**基于**: `realtime-alerting-monitoring-analysis-and-implementation.md` §15 分阶段实施路线图
**前置条件**: Phase 1 + Phase 2 + Phase 3 全部完成
**目标**: 实现告警聚合去重、根因分析、自愈修复、运维知识库、统计大屏

---

## 📋 Phase 4 范围定义

### 本阶段交付物

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | **告警聚合与去重引擎** | 同一问题多告警合并、抑制风暴、智能分组 |
| 2 | **告警关联与根因分析** | 基于拓扑/时序的关联分析，定位根因节点 |
| 3 | **自愈/自动修复机制** | 可配置的自动修复动作（重启服务/清理磁盘/扩容） |
| 4 | **运维知识库 + 智能推荐** | 历史告警→解决方案沉淀，相似告警自动推荐方案 |
| 5 | **多维度报表 & 统计大屏 API** | MTTA/MTTR/SLA 等核心指标聚合展示 |

### 不在本阶段范围

- Grafana/Prometheus 集成 (后续独立项目)
- Vue3 前端重构
- 多租户权限体系

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────┐
│                   Phase 4 新增组件                    │
├──────────┬──────────┬──────────┬──────────┬─────────┤
│ Alert    │ Alert    │ Auto     │ Runbook  │ Report  │
│ Aggregator│ Correlator│ Remedy  │ KB       │ Engine │
│ 聚合引擎  │ 关联分析  │ 自愈修复  │ 知识库   │ 报表API │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬───┘
     │          │          │          │          │
     ▼          ▼          ▼          ▼          ▼
 ┌──────────────────────────────────────────────────┐
 │              Phase 1~3 已有基础层                  │
 │  RuleEngine / AnomalyDetector / Notification /   │
 │  WebSocket / API / Admin / Celery                │
 └──────────────────────────────────────────────────┘
```

---

## 🔧 Step 1: 告警聚合与去重引擎

### 1.1 数据模型

```python
# monitoring/models.py 新增

class AlertGroup(models.Model):
    name = models.CharField(max_length=255, verbose_name='聚合组名')
    fingerprint = models.CharField(max_length=64, unique=True, db_index=True, verbose_name='指纹')
    status = models.CharField(max_length=20, default='firing',
        choices=[('firing','触发中'),('resolved','已解决')], db_index=True)
    severity = models.CharField(max_length=10, default='P2')
    alert_count = models.IntegerField(default=0, verbose_name='告警总数')
    first_fired_at = models.DateTimeField(auto_now_add=True)
    last_fired_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ['-last_fired_at']
        verbose_name = '告警聚合组'
        verbose_name_plural = '告警聚合组'

    def __str__(self):
        return f"[{self.status}] {self.name} ({self.alert_count}次)"
```

### 1.2 聚合服务

文件: `monitoring/aggregation/alert_aggregator.py`

核心逻辑：
- **指纹生成**: 基于 `(rule_id + server_id + metric_name)` 生成 MD5 指纹
- **时间窗口**: 默认 15 分钟内同一指纹的告警合并到同一组
- **计数递增**: 相同指纹新告警 → `alert_count += 1`, 更新 `last_fired_at`
- **自动解决**: 组内所有子告警 resolved 后标记组为 resolved
- **风暴抑制**: 单服务器 5 分钟内 > 20 条告警 → 触发风暴模式，静默低优先级

### 1.3 Admin 注册

在 `monitoring/admin.py` 中注册 `AlertGroup`，显示聚合组列表。

---

## 🔗 Step 2: 告警关联与根因分析

### 2.1 关联规则模型

```python
# monitoring/models.py 新增

class AlertCorrelationRule(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    trigger_patterns = models.JSONField(default=dict, verbose_name='触发条件组合')
    root_cause_hint = models.CharField(max_length=500, verbose_name='根因提示')
    suggested_action = models.TextField(blank=True, verbose_name='建议操作')
    confidence_weight = models.FloatField(default=0.8, verbose_name='置信度权重')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = '告警关联规则'
        verbose_name_plural = '告警关联规则'
```

### 2.2 关联分析引擎

文件: `monitoring/correlation/correlator.py`

算法：
1. **时间窗口聚类**: 30 秒内同时触发的告警归为一簇
2. **拓扑传播分析**: 若 A→B 有依赖关系且 A 先报警，A 为候选根因
3. **指标因果链**: CPU↑ → 内存↑ → 磁盘IO↑ 形成因果链，取链首为根因
4. **历史匹配**: 与 `AlertCorrelationRule` 的 `trigger_patterns` 模式匹配
5. **输出**: 根因告警 ID + 置信度 + 关联告警列表 + 推理路径

### 2.3 API 端点

```
GET  /api/monitoring/correlation/groups/         — 当前活跃关联组
GET  /api/monitoring/correlation/<group_id>/      — 关联详情+根因
POST /api/monitoring/correlation/rules/           — 创建关联规则
```

---

## 🤖 Step 3: 自愈/自动修复机制

### 3.1 数据模型

```python
# monitoring/models.py 新增

class RemediationAction(models.Model):
    name = models.CharField(max_length=200, verbose_name='动作名称')
    action_type = models.CharField(max_length=50,
        choices=[
            ('script','执行脚本'),
            ('service_restart','重启服务'),
            ('disk_cleanup','磁盘清理'),
            ('scale_out','扩容'),
            ('webhook','调用Webhook'),
            ('custom','自定义'),
        ])
    target_command = models.TextField(verbose_name='目标命令/脚本')
    severity_filter = models.CharField(max_length=20, default='P1,P2',
        help_text='适用此动作的告警级别')
    timeout_seconds = models.IntegerField(default=300, verbose_name='超时秒数')
    max_retries = models.IntegerField(default=1, verbose_name='最大重试')
    is_dangerous = models.BooleanField(default=False, verbose_name='危险操作(需确认)')
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = '修复动作'
        verbose_name_plural = '修复动作'

class RemediationHistory(models.Model):
    alert_event = models.ForeignKey(AlertEvent, on_delete=models.CASCADE)
    action = models.ForeignKey(RemediationAction, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='pending',
        choices=[('pending','待执行'),('running','执行中'),('success','成功'),
                 ('failed','失败'),('timeout','超时'),('cancelled','已取消')])
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    output = models.TextField(blank=True, verbose_name='执行输出')
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']
        verbose_name = '修复记录'
        verbose_name_plural = '修复记录'
```

### 3.2 自愈引擎

文件: `monitoring/remediation/remediation_engine.py`

流程：
1. 告警触发后检查是否有匹配的 `RemediationAction`
2. 匹配条件：`severity in action.severity_filter` 且 `action.is_active`
3. 若 `is_dangerous=True` → 仅记录建议，不自动执行
4. 自动执行 → 创建 `RemediationHistory` → 通过 Celery 异步跑命令
5. 执行完成后更新状态，若失败则触发告警升级通知

### 3.3 内置修复模板

| 场景 | 动作类型 | 目标命令 |
|------|----------|----------|
| 磁盘>90% | disk_cleanup | `find /tmp -type f -mtime +7 -delete && journalctl --vacuum-size=100M` |
| 服务宕机 | service_restart | `systemctl restart {service_name}` |
| 内存泄漏 | script | 自定义清理脚本 |
| CPU持续高 | webhook | 调用扩容接口 |

---

## 📚 Step 4: 运维知识库 + 智能推荐

### 4.1 数据模型

```python
# monitoring/models.py 新增

class RunbookEntry(models.Model):
    title = models.CharField(max_length=300, verbose_name='标题')
    problem_pattern = models.JSONField(default=dict, verbose_name='问题特征模式')
    solution = models.TextField(verbose_name='解决方案')
    category = models.CharField(max_length=50, default='general',
        choices=[('network','网络'),('storage','存储'),('memory','内存'),
                 ('cpu','计算'),('database','数据库'),('application','应用'),
                 ('security','安全'),('general','通用')])
    tags = models.CharField(max_length=300, blank=True, verbose_name='标签(逗号分隔)')
    effectiveness_score = models.FloatField(default=0.0, verbose_name='有效评分')
    usage_count = models.IntegerField(default=0, verbose_name='使用次数')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['-effectiveness_score']
        verbose_name = '运维知识条目'
        verbose_name_plural = '运维知识条目'
```

### 4.2 推荐引擎

文件: `monitoring/runbook/recommender.py`

推荐策略：
1. **精确匹配**: `problem_pattern` 字段与当前告警的 rule_name + metric_name 精确匹配
2. **模糊匹配**: 基于 TF-IDF 向量余弦相似度（使用已有 PgVector 或简单文本匹配）
3. **热度排序**: `effectiveness_score * log(usage_count)` 加权排序
4. **自动学习**: 用户采纳推荐后 `usage_count++`；若告警随后 resolved 则 `score += 0.1`

### 4.3 API 端点

```
GET  /api/monitoring/runbook/search/?q=CPU过高        — 搜索知识库
GET  /api/monitoring/runbook/recommend/?alert_id=123   — 针对告警推荐
POST /api/monitoring/runbook/                          — 新建条目
PUT  /api/monitoring/runbook/<id>/feedback/            — 反馈有效性
```

---

## 📊 Step 5: 多维度报表 & 统计大屏 API

### 5.1 报表 API 设计

文件: `monitoring/api/views.py` 新增视图

#### 5.1.1 核心指标仪表盘

```
GET /api/monitoring/dashboard/overview/
响应:
{
  "servers": {"total": 50, "up": 48, "down": 2},
  "alerts": {
    "firing": 12, "resolved_today": 45,
    "mtta_minutes": 3.2,        // Mean Time To Acknowledge
    "mttr_minutes": 18.5,       // Mean Time To Resolve
    "sla_24h": 99.7             // 可用率%
  },
  "anomalies": {"today": 23, "high_severity": 5},
  "trend": {
    "alerts_7d": [12,8,15,10,9,14,11],
    "anomalies_7d": [3,5,2,6,4,3,5]
  }
}
```

#### 5.1.2 SLA 报表

```
GET /api/monitoring/reports/sla/?range=30d&server_id=
响应:
{
  "period": "30d",
  "sla_by_server": [
    {"server": "web-01", "uptime_pct": 99.95, "downtime_min": 22},
    ...
  ],
  "sla_by_service": [...],
  "overall_sla": 99.82
}
```

#### 5.1.3 告警热力图数据

```
GET /api/monitoring/reports/heatmap/?range=7d
响应:
{
  "matrix": [  // 7天 x 24小时
    [0,2,1,0,...],  // 周一每小时告警数
    ...
  ],
  "max_value": 15,
  "labels": {"days":["周一",...], "hours":["00:00",...]}
}
```

### 5.2 前端大屏组件

在 Dashboard 页面新增"统计概览卡片"区域，展示：
- MTTA / MTTR 数字指标卡
- 7 天告警趋势折线图
- 告警级别分布饼图
- 服务器可用率进度条

---

## 📁 文件变更清单

### 新建文件

| 文件 | 用途 |
|------|------|
| `monitoring/aggregation/__init__.py` | 包初始化 |
| `monitoring/aggregation/alert_aggregator.py` | 聚合去重引擎 |
| `monitoring/correlation/__init__.py` | 包初始化 |
| `monitoring/correlation/correlator.py` | 关联与根因分析 |
| `monitoring/remediation/__init__.py` | 包初始化 |
| `monitoring/remediation/remediation_engine.py` | 自愈修复引擎 |
| `monitoring/runbook/__init__.py` | 包初始化 |
| `monitoring/runbook/recommender.py` | 知识库推荐 |

### 修改文件

| 文件 | 变更内容 |
|------|----------|
| `monitoring/models.py` | 新增 AlertGroup / AlertCorrelationRule / RemediationAction / RemediationHistory / RunbookEntry |
| `monitoring/admin.py` | 注册所有新模型 |
| `monitoring/api/views.py` | 新增 correlation / runbook / dashboard / reports 视图 |
| `monitoring/api/urls.py` | 新增路由 |
| `monitoring/engine/rule_evaluator.py` | 集成聚合器调用 |
| `templates/index.html` | 新增大屏统计区域 |

---

## 📋 执行顺序与依赖关系

```
Step 1 (聚合引擎) ◄── 基础，其他步骤依赖聚合后的告警组
  │
  ├──► Step 2 (关联分析) ◄── 依赖聚合组的告警簇
  │     │
  │     ├──► Step 3 (自愈) ◄── 依赖根因分析结果决定修复策略
  │     │
  │     └──► Step 4 (知识库) ◄── 可并行
  │
  Step 5 (报表API) ◄── 独立，可并行
```

---

## ✅ 验收标准

1. **告警聚合**: 同一问题 15 分钟内重复告警自动合并为一个组，显示计数
2. **风暴抑制**: 单服务器短时间内大量告警时自动进入抑制模式
3. **根因分析**: 关联页面可查看告警簇的根因推断和置信度
4. **自愈修复**: 高危告警可触发预配置的自动修复动作，有完整审计日志
5. **知识推荐**: 告警详情页展示匹配的运维知识条目和解决方案
6. **统计大屏**: Dashboard 展示 MTTA/MTTR/SLA 等核心运营指标
