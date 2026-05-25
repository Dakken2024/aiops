# AiOps "AI 驱动运维自愈引擎" 战略设计文档

**版本**: v2.0
**日期**: 2026-05-25
**定位**: 面向中小企业的 AI 驱动运维自愈引擎 — 轻量、高效、敏捷、智能

---

## 一、战略定位

### 1.1 一句话定位

**"AI 驱动的运维自愈引擎"** — 不是监控平台，不是 CMDB，不是日志平台，而是把指标+日志+链路作为输入，以 AI 诊断+自动自愈为核心输出的"运维大脑"。

### 1.2 与竞品的差异化

| 维度 | BlueKing Lite | 夜莺 | Keep | Spug | OMP | **本项目** |
|------|--------------|------|------|------|-----|-----------|
| AI 诊断深度 | 浅层（聊天） | 无 | 告警降噪 | 无 | 巡检预警 | **多源上下文+置信度驱动** |
| 自愈闭环 | 手动触发 | 无 | Webhook | 脚本执行 | 故障自愈 | **置信度驱动自动/半自动** |
| 日志语义搜索 | 无 | 需Loki | 无 | 无 | 无 | **PgVector 原生** |
| 链路追踪 | 无 | 无 | 无 | 无 | 无 | **轻量 OTLP** |
| 多云监控 | 无 | 需Prometheus | 无 | 无 | 无 | **原生适配器** |
| 部署成本 | 4C8G | 需Prometheus | 轻量 | 轻量 | 4C8G+ | **4C8G+PostgreSQL** |
| 技术栈 | Go+Lua | Go+Prometheus | Python | Python | Go | **Python+Django** |

### 1.3 核心价值主张

中小企业运维团队（5-50人）面临的核心矛盾是：**运维工具要么太重（BlueKing/夜莺需要Prometheus生态），要么太浅（Spug/WeOps没有AI能力），要么太窄（Keep只做告警）**。

本项目的价值主张是：**一个 4C8G 服务器就能部署的 AI 运维大脑，从异常检测到根因诊断到自动修复，全程 AI 驱动，越用越准。**

---

## 二、中小企业 AI 智能运维场景全景

### 2.1 场景优先级矩阵

基于中小企业运维团队的实际工作频率和痛点严重程度，将场景分为四个象限：

```
                        高频
                         │
    ┌────────────────────┼────────────────────┐
    │  P0: 必须做好       │  P1: 做好能显著提效  │
    │                    │                    │
    │  · 告警降噪与聚合   │  · AI根因诊断      │
    │  · 服务器基础监控   │  · 日志关联分析     │
    │  · 告警通知可靠性   │  · 自动修复/自愈    │
    │  · 脚本批量执行    │  · 健康评分巡检     │
    │                    │                    │
 低痛 ├────────────────────┼────────────────────┤ 高痛
    │  P2: 做了锦上添花   │  P3: 做好是杀手级   │
    │                    │                    │
    │  · 配置变更审计    │  · 多源关联诊断     │
    │  · 定时任务管理    │  · 置信度驱动自愈   │
    │  · 移动端运维     │  · 历史案例智能匹配  │
    │  · 应用发布流程    │  · 预测性容量预警   │
    │                    │                    │
    └────────────────────┼────────────────────┘
                        低频
```

### 2.2 中小企业运维的 8 个真实场景

#### 场景 1：半夜告警风暴，运维被电话叫醒

**现状**：50台服务器，某交换机故障导致批量网络超时，5分钟内产生 200+ 条告警，钉钉群被刷屏，运维无法快速定位根因。

**AI 自愈引擎如何解决**：
- 告警聚合：200条告警 → 1个 AlertGroup（"交换机故障导致批量网络超时"）
- 多源关联：指标异常（CPU升高）+ 日志异常（Connection refused）+ 链路异常（超时Span）→ 三源交叉确认
- AI 诊断：综合三源上下文，输出"根因：核心交换机端口故障，影响范围：A机房全部服务器，置信度：0.91"
- 自动修复：置信度 > 0.85，自动执行"切换备用交换机"Runbook
- 结果：运维被叫醒时，问题已自动修复，只需确认结果

#### 场景 2：磁盘即将满，业务随时中断

**现状**：数据库服务器磁盘使用率 87%，按当前增速 3 天后满，但告警阈值设的 90%，还没触发。

**AI 自愈引擎如何解决**：
- 预测性检测：基于 7 天历史数据的趋势预测，提前预警"3天后磁盘将满"
- 日志关联：同时检测到日志中频繁出现 "No space left on device" 警告
- AI 诊断：综合指标趋势+日志模式，输出"根因：/var/log/mysql 慢查询日志未轮转，日增 2GB"
- 自动修复：置信度 0.88，自动执行"轮转MySQL慢查询日志 + 清理30天前日志"
- 结果：在告警触发前就解决了问题

#### 场景 3：应用响应变慢，用户投诉，但指标一切正常

**现状**：CPU/内存/磁盘都正常，但用户反馈页面加载慢。运维只能 SSH 上去手动排查。

**AI 自愈引擎如何解决**：
- 链路追踪：OTLP 接收到的 Span 显示 order-service → db-query 平均耗时从 50ms 升至 800ms
- 日志关联：同一时段出现 "Slow query detected: SELECT * FROM orders WHERE..."
- AI 诊断：综合链路+日志，输出"根因：orders 表缺少索引，查询全表扫描，置信度：0.82"
- 人工确认：置信度 < 0.85，推送钉钉卡片，运维一键确认执行"添加索引"

#### 场景 4：新上线功能导致内存泄漏

**现状**：下午 3 点发布新版本，晚上 8 点开始内存缓慢上升，凌晨 2 点 OOM 崩溃。

**AI 自愈引擎如何解决**：
- 异常检测：动态基线检测到内存使用偏离日周期模式
- 日志关联：检测到 "OutOfMemoryError" + "GC overhead limit exceeded" 日志模式
- 链路关联：新版本接口 /api/v2/recommend 的 Span 显示内存分配异常
- AI 诊断：综合三源，输出"根因：v2/recommend 接口缓存未释放，与今天 15:00 发布关联，置信度：0.79"
- 人工确认：推送诊断结果+建议"回滚至上一版本"，运维确认执行

#### 场景 5：多云环境统一运维

**现状**：本地 20 台服务器 + 阿里云 10 台 ECS + 腾讯云 5 台 CVM，三套监控工具，告警分散。

**AI 自愈引擎如何解决**：
- 多云适配器：统一采集本地+阿里云+腾讯云指标
- 统一告警：所有告警进入同一引擎，跨云关联
- AI 诊断：识别"阿里云 RDS 慢查询影响本地应用"这种跨云关联
- 混合仪表盘：一个页面看全所有资源

#### 场景 6：K8s Pod 频繁重启

**现状**：K8s 集群中某 Deployment 的 Pod 每隔 10 分钟重启一次，但 CPU/内存都正常。

**AI 自愈引擎如何解决**：
- K8s 事件采集：检测到 "Back-off restarting failed container"
- 日志关联：Pod 日志显示 "Health check failed: /healthz timeout"
- 链路关联：健康检查接口的 Span 显示依赖的 Redis 连接超时
- AI 诊断：综合三源，输出"根因：Redis 连接池耗尽导致健康检查失败，置信度：0.86"
- 自动修复：重启 Redis 连接池

#### 场景 7：SSL 证书即将过期

**现状**：10 个域名使用不同厂商证书，过期时间不一，经常忘记续期导致网站不可用。

**AI 自愈引擎如何解决**：
- 自动发现：CMDB 已有 SSL 证书管理 + 到期提醒
- AI 升级：证书到期前 30 天自动创建续期工单，AI 生成续期步骤
- 自动修复：对接 ACME 协议自动续期 Let's Encrypt 证书

#### 场景 8：运维知识传承

**现状**：老运维离职后，新运维不知道怎么处理历史问题，同样的故障反复排查。

**AI 自愈引擎如何解决**：
- 知识反馈循环：每次修复结果自动向量化存入案例库
- 历史案例匹配：新告警发生时，PgVector 检索历史相似案例
- 越用越准：运维人员反馈"有效/无效"，调整推荐权重
- 知识不随人走：所有运维经验沉淀在平台中

---

## 三、技术架构

### 3.1 整体架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                        数据采集层                                  │
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐    │
│  │ Metrics  │  │  Logs    │  │ Traces   │  │ Cloud Metrics │    │
│  │ Agent/SSH│  │ Syslog/  │  │ OTLP     │  │ Aliyun/Tencent│    │
│  │ Push API │  │ Agent    │  │ HTTP     │  │ Adapter       │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘    │
│       │             │             │               │              │
├───────┼─────────────┼─────────────┼───────────────┼──────────────┤
│       ▼             ▼             ▼               ▼              │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              PostgreSQL + PgVector                       │     │
│  │                                                         │     │
│  │  ServerMetric │ LogEntry │ TraceSpan │ CloudResource    │     │
│  │  MetricAgg    │ LogPattern│ SpanAttr │ CaseVector       │     │
│  └─────────────────────────┬───────────────────────────────┘     │
│                            │                                     │
│  数据持久层                 │                                     │
├────────────────────────────┼─────────────────────────────────────┤
│                            ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              Multi-Source Correlator                     │     │
│  │              多源关联引擎                                 │     │
│  │                                                         │     │
│  │  · 时间窗口对齐 (5min)                                  │     │
│  │  · 指标异常 ↔ 日志异常 ↔ 链路异常                       │     │
│  │  · PgVector 语义相似度匹配                              │     │
│  │  · 历史案例向量检索 (CaseVector)                        │     │
│  └─────────────────────────┬───────────────────────────────┘     │
│                            │                                     │
│  智能分析层                 ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              AI Diagnosis Engine v2                      │     │
│  │              AI 诊断引擎 (升级版)                         │     │
│  │                                                         │     │
│  │  输入: 指标上下文 + 关联日志摘要                         │     │
│  │       + 关联链路片段 + 历史相似案例                      │     │
│  │  输出: 根因分析 + 置信度 + 修复建议                      │     │
│  │       + 预估影响范围 + 根因分类                          │     │
│  └──────────┬──────────────────────────────┬────────────────┘     │
│             │                              │                      │
│             ▼                              ▼                      │
│  ┌──────────────────┐  ┌──────────────────────────┐              │
│  │ Auto-Remediate   │  │ Human-Confirm            │              │
│  │ 高信心自动修复    │  │ 低信心人工确认            │              │
│  │ (置信度 ≥ 0.85)  │  │ (置信度 < 0.85)          │              │
│  │ + 历史成功案例   │  │ → 钉钉/企微卡片确认      │              │
│  └────────┬─────────┘  └────────────┬─────────────┘              │
│           │                         │                             │
│  自动化层  ▼                         ▼                             │
│  ┌─────────────────────────────────────────────────────────┐     │
│  │              Knowledge Feedback Loop                     │     │
│  │              知识反馈循环                                 │     │
│  │                                                         │     │
│  │  · 修复结果 → 更新 Runbook 评分                          │     │
│  │  · 根因+修复 → 向量化存入 CaseVector                    │     │
│  │  · 越用越准的 AI 诊断                                    │     │
│  └─────────────────────────────────────────────────────────┘     │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│                        基础设施层                                  │
│  Django + Celery + Redis(dev)/RabbitMQ(prod) + PostgreSQL+PgVec  │
│  Daphne ASGI + Nginx + Paramiko SSH                             │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 技术栈约束

| 类别 | 技术选型 | 说明 |
|------|----------|------|
| **核心框架** | Django + Celery + PostgreSQL | 不变 |
| **向量检索** | PgVector | PostgreSQL 扩展，零新增中间件 |
| **消息队列** | RabbitMQ(生产) + Redis(开发) | Celery Broker |
| **AI 引擎** | OpenAI SDK (Qwen/DeepSeek/GPT) | 不变 |
| **异常检测** | NumPy/SciPy/scikit-learn/statsmodels | 不变 |
| **SSH 执行** | Paramiko | 不变 |
| **K8s 交互** | Kubernetes Python Client | 不变 |
| **云 SDK** | aliyun-python-sdk / tencentcloud-sdk-python | 不变 |
| **链路接收** | OpenTelemetry HTTP (OTLP) | 新增，纯 HTTP 接收 |
| **前端** | Django Templates + Bootstrap 4 + ECharts 5 | 不变 |

**不引入的中间件**：Elasticsearch、ClickHouse、Jaeger、Prometheus、Loki、Kafka

### 3.3 数据模型设计

#### LogEntry — 日志条目

```python
class LogEntry(models.Model):
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE,
        related_name='log_entries')
    timestamp = models.DateTimeField(db_index=True)
    level = models.CharField(max_length=10, db_index=True)
    source = models.CharField(max_length=50, default='syslog')
    message = models.TextField()
    message_vector = pgvector.VectorField(dimensions=1536, null=True)
    structured_data = models.JSONField(default=dict)
    is_anomaly = models.BooleanField(default=False, db_index=True)
    pattern_id = models.IntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['server', '-timestamp']),
            models.Index(fields=['level', '-timestamp']),
            GinIndex(fields=['message_vector']),
        ]
```

#### LogPattern — 日志模式

```python
class LogPattern(models.Model):
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True)
    pattern_template = models.TextField()
    pattern_vector = pgvector.VectorField(dimensions=1536, null=True)
    level = models.CharField(max_length=10)
    source = models.CharField(max_length=50)
    occurrence_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField()
    last_seen = models.DateTimeField()
    is_anomaly_pattern = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [GinIndex(fields=['pattern_vector'])]
```

#### TraceSpan — 链路追踪

```python
class TraceSpan(models.Model):
    trace_id = models.CharField(max_length=32, db_index=True)
    span_id = models.CharField(max_length=16)
    parent_span_id = models.CharField(max_length=16, null=True, blank=True)
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True)
    service_name = models.CharField(max_length=100, db_index=True)
    operation = models.CharField(max_length=200)
    start_time = models.DateTimeField(db_index=True)
    duration_ms = models.IntegerField(default=0)
    status = models.CharField(max_length=10, default='OK', db_index=True)
    error_message = models.TextField(blank=True)
    attributes = models.JSONField(default=dict)
    span_vector = pgvector.VectorField(dimensions=1536, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['service_name', '-start_time']),
            models.Index(fields=['status', '-start_time']),
            GinIndex(fields=['span_vector']),
        ]
```

#### CaseVector — 历史案例向量库

```python
class CaseVector(models.Model):
    title = models.CharField(max_length=200)
    symptoms = models.TextField(help_text="症状描述：指标异常+日志模式+链路特征")
    root_cause = models.TextField()
    remediation = models.TextField()
    confidence = models.FloatField(default=0.0)
    effectiveness_score = models.FloatField(default=0.0)
    usage_count = models.PositiveIntegerField(default=0)
    symptom_vector = pgvector.VectorField(dimensions=1536, null=True)
    related_alert_rules = models.JSONField(default=list)
    related_runbook = models.ForeignKey('monitoring.RunbookEntry',
        on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [GinIndex(fields=['symptom_vector'])]
```

### 3.4 AI Diagnosis v2 Prompt 模板

```
你是一名资深运维工程师，请根据以下多源上下文信息进行根因分析。

## 告警信息
- 服务器: {hostname} ({ip_address})
- 告警规则: {rule_name}
- 指标: {metric_name} 当前值={current_value} 阈值={threshold}
- 严重程度: {severity}
- 触发时间: {fired_at}

## 指标上下文 (最近20个采样点)
{metric_samples}

## 关联日志异常 (告警前后5分钟, ERROR/WARN)
{related_logs}

## 关联链路异常 (告警前后5分钟, ERROR/慢调用)
{related_traces}

## 历史相似案例
{similar_cases}

请输出JSON格式:
{
  "root_cause": "根因分析",
  "root_cause_category": "分类(network/disk/memory/cpu/service/config/unknown)",
  "confidence": 0.0-1.0,
  "impact_scope": "影响范围评估",
  "remediation_suggestion": "修复建议",
  "remediation_command": "可执行的修复命令(如有)",
  "is_dangerous": false,
  "urgency": "high/medium/low",
  "reasoning": "分析推理过程"
}
```

---

## 四、实施路线图

### Phase 6 (已完成): 云平台集成与数据管道优化

### Phase 6.5: PostgreSQL + PgVector 基础设施 (2周)

| 任务 | 说明 |
|------|------|
| 安装 PgVector 扩展 | `CREATE EXTENSION vector;` |
| 添加 pgvector Python 包 | `pip install pgvector` |
| 配置 Django PgVector | settings.py 配置 |
| 迁移 RabbitMQ | 生产环境 Celery Broker 从 Redis 切换到 RabbitMQ |
| 数据库优化 | ServerMetric 分区表 + 索引优化 |

### Phase 7: 多源数据采集与存储 (3周)

| 任务 | 说明 |
|------|------|
| LogEntry 模型 + 迁移 | 日志条目存储 |
| LogPattern 模型 + 迁移 | 日志模式聚类 |
| TraceSpan 模型 + 迁移 | 链路追踪存储 |
| CaseVector 模型 + 迁移 | 历史案例向量库 |
| Agent 日志采集 | SSH tail + Syslog UDP 接收 |
| OTLP HTTP Receiver | 接收 OpenTelemetry 链路数据 |
| 日志向量化 Celery 任务 | 调用 Embedding API 生成向量 |
| 日志模式挖掘 Celery 任务 | Drain 算法聚类日志模式 |
| 数据保留策略扩展 | LogEntry 7天 + TraceSpan 14天 |

### Phase 8: Multi-Source Correlator + AI Diagnosis v2 (3周)

| 任务 | 说明 |
|------|------|
| Multi-Source Correlator | 多源关联引擎（时间窗口对齐+三源交叉） |
| PgVector 语义检索 | 历史案例相似度匹配 |
| AI Diagnosis v2 Prompt | 多源上下文 Prompt 模板 |
| 置信度驱动自愈决策 | ≥0.85自动 / <0.85人工确认 |
| 知识反馈循环 | 修复结果→CaseVector 向量化存储 |
| 钉钉/企微交互卡片 | 一键确认/拒绝修复 |
| 多源关联仪表盘 | 指标+日志+链路联动展示 |

### Phase 9: 预测性运维 + 生态扩展 (4周)

| 任务 | 说明 |
|------|------|
| 容量预测 | 基于历史趋势预测资源耗尽时间 |
| 智能基线 | 自动学习日/周周期模式 |
| Prometheus RemoteWrite | 接收 Prometheus 指标数据 |
| Webhook 出站 | 告警/事件 Webhook 通知 |
| OpenAPI 文档 | DRF Schema + Swagger UI |
| 移动端告警卡片 | 钉钉/企微小程序嵌入 |

---

## 五、中小企业选择路径

### 路径 A："从零快速构建" — 本项目为首选

```
AiOps 自愈引擎 (4C8G 部署)
    ├── 监控: 内置 Agent + 多云适配器
    ├── 告警: 6种规则 + 聚合降噪 + 多通道通知
    ├── AI诊断: 多源上下文 + 置信度驱动
    ├── 自愈: 自动修复 + 人工确认
    ├── 日志: PgVector 语义搜索
    ├── 链路: 轻量 OTLP 接收
    └── 知识: 越用越准的案例库
```

### 路径 B："强化现有系统" — 本项目作为"AI 大脑"补充

```
现有 Prometheus + Grafana (监控)
现有 Spug (脚本执行/发布)
    ↓ 接入
AiOps 自愈引擎 (AI 大脑角色)
    ├── 接收 Prometheus AlertManager 告警
    ├── 接收现有日志 (Syslog 转发)
    ├── AI 多源诊断 + 根因分析
    ├── 调用 Spug API 执行修复脚本
    └── 知识沉淀 + 案例积累
```

### 路径 C："专项工具组合" — 本项目做核心大脑

```
Netdata (实时监控) → AiOps (AI大脑) → Spug (脚本执行)
Graylog (日志平台) ↗              ↘ 钉钉/企微 (通知)
SkyWalking (APM)  ↗
```

---

## 六、成功指标

| 指标 | 当前 | 目标 (6个月) |
|------|------|-------------|
| AI 诊断准确率 | ~60% (仅指标) | ≥85% (多源) |
| 自动修复成功率 | ~40% | ≥75% |
| 告警降噪率 | ~30% (聚合) | ≥70% (聚合+AI过滤) |
| 平均修复时间 (MTTR) | 30-60分钟 | ≤10分钟 |
| 误报率 | ~25% | ≤10% |
| 部署资源 | 4C8G | 4C8G (不变) |
| 单机支持服务器数 | 100台 | 500台 |

---

> **核心理念**: AI 时代的运维不是"更多工具"，而是"更聪明的工具"。本项目坚持做轻量、做深度、做闭环——让中小企业用一台服务器、一个平台，就能拥有从检测到自愈的 AI 运维能力。
