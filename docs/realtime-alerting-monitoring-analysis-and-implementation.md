# AiOps 实时预警与监控系统分析报告 & 落地实施方案

**文档版本**: v1.0  
**创建日期**: 2026-04-13  
**适用项目**: AiOps 智能运维平台 (Django 5.x)  
**文档性质**: 现状深度分析 + 企业级落地实施指南

---

## 📋 目录

1. [执行摘要](#1-执行摘要)
2. [现有实现深度分析](#2-现有实现深度分析)
3. [能力成熟度评估矩阵](#3-能力成熟度评估矩阵)
4. [行业最佳实践对比](#4-行业最佳实践对比)
5. [落地实施方案 - 架构设计](#5-落地实施方案---架构设计)
6. [核心模块一：可配置预警规则引擎](#6-核心模块一可配置预警规则引擎)
7. [核心模块二：实时数据采集增强](#7-核心模块二实时数据采集增强)
8. [核心模块三：异常检测算法库](#8-核心模块三异常检测算法库)
9. [核心模块四：智能告警通知中心](#9-核心模块四智能告警通知中心)
10. [核心模块五：监控数据可视化平台](#10-核心模块五监控数据可视化平台)
11. [数据库模型设计](#11-数据库模型设计)
12. [API 接口规范](#12-api-接口规范)
13. [前端组件设计](#13-前端组件设计)
14. [高可用与扩展性设计](#14-高可用与扩展性设计)
15. [分阶段实施路线图](#15-分阶段实施路线图)
16. [附录：完整代码示例](#16-附录完整代码示例)

---

## 1. 执行摘要

### 1.1 分析结论

经过对 AiOps 项目全部源码的逐文件深度审查，**当前项目在实时预警和监控领域的实现处于"基础采集 + 极简告警"阶段，距离企业级生产就绪的监控系统存在显著差距。**

具体而言：
- ✅ **已具备**: 基础指标采集 (CPU/内存/磁盘/网络/负载)、SSL证书过期检测、钉钉/企微Webhook通知、AI辅助诊断
- ⚠️ **部分具备**: Dashboard趋势图表展示、K8s集群监控采集、Agent部署机制
- ❌ **完全缺失**: 预警规则引擎、阈值配置UI、异常检测算法、告警聚合/静默/升级、多渠道通知模板、时序数据库集成、Prometheus/Grafana标准栈

### 1.2 核心差距量化

| 能力维度 | 行业标准 | 当前状态 | 差距等级 |
|---------|---------|---------|---------|
| **规则引擎** | 支持多条件组合、动态阈值、周期检测 | 仅SSL硬编码阈值 | 🔴 严重缺失 |
| **异常检测** | 统计基线+ML算法自动发现异常 | 无任何异常检测 | 🔴 完全空白 |
| **告警管理** | 聚合/去重/静默/升级/确认闭环 | 单条发送无管理 | 🔴 严重缺失 |
| **数据存储** | TSDB (InfluxDB/Prometheus/TimescaleDB) | SQLite常规表存储 | 🟠 性能瓶颈 |
| **可视化** | Grafana仪表盘+自定义Widget | Django模板简单图表 | 🟠 功能有限 |
| **通知渠道** | 10+渠道(邮件/短信/语音/Webhook/Slack等) | 仅钉钉+企微2个 | 🟠 渠道单一 |
| **配置性** | UI界面动态配置所有规则参数 | 代码硬编码 | 🔴 无法配置 |

---

## 2. 现有实现深度分析

### 2.1 数据采集层 (Data Collection) — 已实现 ⭐⭐⭐☆☆

#### 2.1.1 服务器指标采集架构

**核心文件**: [run_agent.py](file:///d:/codes/aiops/cmdb/management/commands/run_agent.py)

```
┌─────────────────────────────────────────────────────────────┐
│                    APScheduler (60s interval)                │
│  ┌─────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │ ThreadPool  │───▶│ Server List   │───▶│ Collect Loop   │  │
│  │ Executor    │    │ (Running)     │    │ (max 100线程)  │  │
│  └─────────────┘    └──────────────┘    └───────┬────────┘  │
│                                                │            │
│                    ┌───────────────────────────┼────────┐   │
│                    ▼                           ▼        │   │
│           ┌────────────────┐          ┌──────────────┐   │   │
│           │ Mode A: Agent  │          │ Mode B: SSH   │   │   │
│           │ HTTP Pull      │          │ Paramiko连接   │   │   │
│           │ :10050/metrics │          │ 组合命令链式   │   │   │
│           └───────┬────────┘          └──────┬───────┘   │   │
│                   ▼                          ▼           │   │
│           ┌──────────────────────────────────────────┐   │   │
│           │         ServerMetric Model 入库           │   │   │
│           │ CPU/Mem/Disk/Load/NetIn/NetOut/DiskIO    │   │   │
│           └──────────────────────────────────────────┘   │   │
└─────────────────────────────────────────────────────────────┘
```

**采集指标详情** (来自 [agent_code.py](file:///d:/codes/aiops/cmdb/agent_code.py)):

| 指标名称 | 字段 | 采集方式 | 粒度 | 备注 |
|---------|------|---------|------|------|
| CPU使用率 | `cpu_usage` | `psutil.cpu_percent()` | % | us+sy |
| 内存使用率 | `mem_usage` | `psutil.virtual_memory().percent` | % | 物理内存 |
| 磁盘使用率 | `disk_usage` | `psutil.disk_usage('/')` | % | 仅根分区 |
| 系统负载 | `load_1min` | `psutil.getloadavg()[0]` | 数值 | 1分钟均值 |
| 入站流量 | `net_in` | `/proc/net/dev`差值 | KB/s | 所有网卡合计 |
| 出站流量 | `net_out` | `/proc/net/dev`差值 | KB/s | 所有网卡合计 |
| 磁盘读取速率 | `disk_read_rate` | `/proc/diskstats`差值 | KB/s | 所有磁盘合计 |
| 磁盘写入速率 | `disk_write_rate` | `/proc/diskstats`差值 | KB/s | 所有磁盘合计 |

**K8s集群采集** (来自 [collect_k8s.py](file:///d:/codes/aiops/k8s_manager/management/commands/collect_k8s.py)):
- 通过 K8s API 获取节点列表 → 并发拉取各节点 Agent 指标 → 存入 `NodeSnapshot`
- 60秒间隔, 最大20并发线程
- 采集内容: CPU/Mem/Disk/NetIn/NetOut/DiskIO + Kubelet日志/Proxy日志/Runtime状态

#### 2.1.2 采集层优势分析

```python
# 优势 1: 双模式采集 (Agent优先 + SSH兜底)
if server.use_agent:
    # Agent模式: HTTP GET /metrics, <100ms延迟
    resp = requests.get(agent_url, timeout=3)
else:
    # SSH模式: Paramiko组合命令, 单次RTT获取全部指标
    cmd_chain = "top -bn1... ||| free -m... ||| df -h..."
```

```python
# 优势 2: 高效命令聚合 (SSH模式下一次交互获取8组数据)
cmd_chain = (
    "top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'; "
    "echo '|||'; "
    "free -m | grep Mem | awk '{print $3/$2 * 100.0}'; "
    # ... 共8个命令用 ||| 分隔, 减少RTT次数
)
```

```python
# 优势 3: 动态线程池调整
worker_num = min(count, 100)  # 根据服务器数量自适应
with ThreadPoolExecutor(max_workers=worker_num) as executor:
    executor.map(collect_single_server, server_ids)
```

#### 2.1.3 采集层不足之处

| 问题 | 影响 | 严重程度 |
|------|------|---------|
| **无自定义指标支持** | 只能采集内置8项指标，无法扩展业务指标 | 🟠 中 |
| **无标签(Tag)体系** | 缺少环境/区域/业务线等维度标签 | 🟠 中 |
| **无数据质量校验** | 异常值(如CPU>100%)直接入库无过滤 | 🟡 低 |
| **无采集健康度上报** | Agent失活无自检机制 | 🟡 低 |
| **SQLite性能瓶颈** | 百万级ServerMetric写入将严重降级 | 🔴 高 |
| **无降级策略** | 单点故障导致整批数据丢失 | 🟠 中 |

---

### 2.2 预警规则引擎 (Alert Rule Engine) — 几乎空白 🔴

#### 2.2.1 当前唯一告警: SSL证书过期检测

**核心文件**: [tasks.py](file:///d:/codes/aiops/cmdb/tasks.py) (第30-102行)

```python
@shared_task
def check_ssl_certificates_task():
    """Celery 定时任务：批量检测证书"""
    certs = SSLCertificate.objects.all()
    for c in certs:
        cert_data, error = get_cert_info(c.domain, c.port)
        
        # ... 解析证书过期时间 ...
        
        # 触发告警 (剩余 < 15 天) ← 硬编码阈值!
        if c.auto_alert and remaining < 15:
            send_alert(c.domain, remaining)
```

**问题清单**:

```python
# 问题 1: 阈值硬编码为 15 天，不可配置
if c.auto_alert and remaining < 15:  # ← 写死在代码里!

# 问题 2: 只有1种告警条件 (时间阈值)，不支持多条件组合
# 不存在: AND/OR 条件组合
# 不存在: 滑动窗口统计 (如"连续3次超过阈值")
# 不存在: 百分比变化检测 (如"CPU比昨天同时段增长50%")

# 问题 3: 无规则优先级/严重级别
# 所有告警都是同一个级别，无法区分 P0/P1/P2

# 问题 4: 无告警抑制/静默机制
# 同一个问题可能每分钟重复告警 (如果检查频率过高)
```

#### 2.2.2 缺失的核心引擎组件

```
┌──────────────────────────────────────────────────────────────┐
│                  ❌ 缺失的规则引擎组件                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ 规则定义器   │  │ 条件评估器   │  │ 触发控制器       │  │
│  │ (Rule DSL)   │→ │ (Condition   │→ │ (Throttle/       │  │
│  │              │  │  Evaluator)  │  │  Aggregate/      │  │
│  │ • 静态阈值   │  │              │  │  Suppress)       │  │
│  │ • 动态基线   │  │ • 单点比较   │  │                  │  │
│  │ • 复合条件   │  │ • 窗口统计   │  │ • 冷却期CoolDown │  │
│  │ • 周期检测   │  │ • 趋势预测   │  │ • 分组分流       │  │
│  └──────────────┘  └──────────────┘  │ • 告警升级       │  │
│                                       └──────────────────┘  │
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ 规则版本控制 │  │ 规则测试沙箱 │  │ 规则依赖关系图   │  │
│  │ (Versioning) │  │ (Dry Run)    │  │ (Dependency      │  │
│  │              │  │              │  │  Graph)          │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### 2.3 异常检测算法 (Anomaly Detection) — 完全空白 🔴

**当前状态**: 项目中不存在任何形式的自动化异常检测。

**AI辅助诊断 ≠ 异常检测**:
- 现有的 AI 诊断功能 ([ai_ops/views.py](file:///d://codes/aiops/ai_ops/views.py) 的 `diagnose_server`) 是**被动触发式**的人工请求分析
- 它需要用户手动点击"诊断"按钮，然后调用 LLM 分析最近20分钟的数据
- 这不是真正的实时异常检测

**真正缺失的能力**:

| 检测类型 | 描述 | 典型场景 | 当前状态 |
|---------|------|---------|---------|
| **静态阈值检测** | 固定阈值越界报警 | CPU > 90% | ❌ 未实现 |
| **动态基线检测** | 与历史同期对比偏差 | 流量比上周同期 > 3σ | ❌ 未实现 |
| **趋势预测检测** | ARIMA/LSTM预测未来值 | 内存持续增长即将溢出 | ❌ 未实现 |
| **同环比检测** | 日/周/月对比异常 | 磁盘日增长量突增10x | ❌ 未实现 |
| **拓扑关联检测** | 关联指标联动分析 | DB慢查询 → CPU飙升 → 连接池满 | ❌ 未实现 |
| **季节性检测** | 识别周期性模式 | 业务波峰/波谷识别 | ❌ 未实现 |
| **离群点检测** | Isolation Forest等 | 单台服务器行为偏离群体 | ❌ 未实现 |

---

### 2.4 告警通知系统 (Notification System) — 基础实现 ⭐☆☆☆☆

#### 2.4.1 现有通知实现

**核心文件**: [tasks.py](file:///d:/codes/aiops/cmdb/tasks.py) 第30-55行

```python
def send_alert(domain, days, error=None):
    """发送告警 (钉钉/企微)"""
    # 从系统配置中读取 Webhook URL
    ding_url = SystemConfig.objects.filter(key='dingtalk_webhook').first()
    wechat_url = SystemConfig.objects.filter(key='wechat_webhook').first()

    msg_title = f"🚨 SSL证书告警: {domain}"
    msg_content = f"域名: {domain}\n状态: 即将过期\n剩余天数: {days} 天"

    # 发送钉钉
    if ding_url and ding_url.value:
        requests.post(ding_url.value, json={
            "msgtype": "text",
            "text": {"content": f"{msg_title}\n{msg_content}"}
        }, timeout=5)

    # 发送企业微信
    if wechat_url and wechat_value:
        requests.post(wechat_url.value, json={...}, timeout=5)
```

#### 2.4.2 通知系统缺陷分析

| 维度 | 行业标准 | 当前实现 | 差距 |
|------|---------|---------|------|
| **渠道数量** | 10+ (邮件/短信/电话/Slack/Telegram/飞书/PagerDuty...) | 2 (钉钉/企微) | 差8+个渠道 |
| **消息格式** | Markdown卡片/Interactive按钮/图片附件 | 纯文本 | 无富媒体 |
| **路由策略** | 按严重级别/值班表/Escalation链路分发 | 全部发送给同一群 | 无分级 |
| **静默维护** | 计划内维护期间自动屏蔽告警 | 无 | 全时段告警 |
| **确认闭环** | Acknowledge → Resolve → 评论 | 无跟踪 | 开环无反馈 |
| **聚合去重** | 相似告警合并为1条通知 | 可能重复轰炸 | 用户体验差 |
| **发送可靠性** | 重试队列/死信队列/限流保护 | try-except pass吞掉异常 | 静默失败 |
| **模板系统** | 多语言/多角色模板 | 硬编码字符串 | 不可定制 |

**关键代码缺陷**:
```python
# 缺陷 1: 异常被静默吞掉
try:
    requests.post(ding_url.value, json={...}, timeout=5)
except:
    pass  # ← 告警发送失败完全无感知!

# 缺陷 2: 无重试机制
# 如果网络抖动导致发送失败，告警直接丢失

# 缺陷 3: 无发送日志
# 不知道哪些告警成功发送了，哪些失败了

# 缺陷 4: Webhook URL明文存储在SystemConfig中
# 无加密保护，有安全风险
```

---

### 2.5 数据可视化 (Visualization) — 基础Dashboard ⭐⭐☆☆☆

#### 2.5.1 现有Dashboard实现

**核心文件**: [system/views.py](file:///d:/codes/aiops/system/views.py) 的 `dashboard()` 函数

**功能清单**:
- ✅ 服务器选择下拉框 (单机视图 vs 集群平均视图)
- ✅ 实时数值展示 (CPU%/内存%/健康度/在线率)
- ✅ 趋势折线图 (最近20个采样点 ≈ 20分钟)
- ✅ 图表类型: CPU/内存/入网流量/出网流量/磁盘使用/磁盘读写
- ✅ 权限过滤 (RBAC分组可见性)
- ✅ AI模型选择器 (用于手动触发诊断)

#### 2.5.2 可视化差距分析

```
当前 Dashboard (基础版):                    企业级监控面板 (目标):
┌──────────────────────┐                   ┌────────────────────────────────┐
│  CPU: 45%  MEM: 62%  │                   │ ┌──────┐ ┌──────┐ ┌──────┐     │
│  ─────────────────   │                   │ │Topology│ │Heatmap│ │Gauge │     │
│  ~~~~~~~~/~~~~~~~~~~ │                   │ │ Map   │ │      │ │Chart │     │
│  ~~~~~~~~/\~~~~~~~~~ │                   │ └──────┘ └──────┘ └──────┘     │
│  (简单折线图)         │                   │                                │
│                      │                   │ ┌──────────────────────────┐  │
│  Net In/Out:         │                   │ │ Alert Table (可筛选/排序) │  │
│  ~~~~~~~~~~~~~~~~~   │                   │ │ ● P0: CPU>95% web-01     │  │
│  ~~~~~~~~~~~~~~~~~   │                   │ │ ● P1: Disk>90% db-02     │  │
│  (简单折线图)         │                   │ │ ● P2: SSL cert expiring   │  │
│                      │                   │ └──────────────────────────┘  │
│  [诊断] 按钮          │                   │                                │
└──────────────────────┘                   │ ┌─────┐ ┌─────┐ ┌─────────┐  │
                                           │ │Trend│ │Compare│ │Forecast │  │
                                           │ │View│ │Mode  │ │Chart    │  │
                                           │ └─────┘ └─────┘ └─────────┘  │
                                           └────────────────────────────────┘
```

**具体缺失项**:

| 可视化能力 | 描述 | 当前状态 |
|-----------|------|---------|
| **实时刷新** | WebSocket推送最新数据 | ❌ 页面需手动刷新 |
| **时间范围选择** | 1h/6h/24h/7d/30d | ❌ 固定20条记录 |
| **多维度下钻** | 从集群→机房→主机→进程 | ❌ 仅单机/集群两级 |
| **告警叠加** | 图表上标注告警发生时刻 | ❌ 无告警标记 |
| **对比视图** | 同指标多机器并排对比 | ❌ 不支持 |
| **Top N 排行** | CPU/内存Top10热力图 | ❌ 不支持 |
| **导出功能** | PDF报告/CSV数据导出 | ❌ 不支持 |
| **自定义布局** | 用户拖拽排列Widget | ❌ 固定布局 |

---

### 2.6 AI辅助能力 (AI-Assisted Analysis) — 有亮点 ⭐⭐⭐⭐☆

这是当前项目中**最具差异化价值**的部分：

| AI功能 | 文件位置 | 实现质量 | 说明 |
|--------|---------|---------|------|
| **服务器故障诊断** | [ai_ops/views.py:diagnose_server()](file:///d:/codes/aiops/ai_ops/views.py) | ⭐⭐⭐⭐ | 取20分钟指标→LLM分析→给出建议 |
| **SSH审计分析** | [ai_ops/views.py:audit_terminal_log()](file:///d:/codes/aiops/ai_ops/views.py) | ⭐⭐⭐⭐ | 终端录像→安全评分0-100 |
| **高危命令风险评估** | [ai_ops/views.py:assess_risk()](file:///d:/codes/aiops/ai_ops/views.py) | ⭐⭐⭐⭐ | 破坏性/可逆性/替代方案评估 |
| **自然语言转Shell** | [ai_ops/views.py:generate_command()](file:///d:/codes/aiops/ai_ops/views.py) | ⭐⭐⭐⭐ | NL→可执行命令 |
| **日志解释** | [ai_ops/views.py:explain_log()](file:///d:/codes/aiops/ai_ops/views.py) | ⭐⭐⭐ | 截取日志→原因+解决方案 |
| **AI对话助手** | [ai_ops/views.py:chat_index/send_msg()](file:///d:/codes/aiops/ai_ops/views.py) | ⭐⭐⭐ | 通用运维问答 |

**关键亮点**: WebSSH中的实时高危命令拦截 ([consumers.py](file:///d:/codes/aiops/cmdb/consumers.py))
```python
# 正则匹配高危命令模式
patterns = [
    r'(?:^|[;&|\s])rm\s+.*(?:-[a-zA-Z]*[rR]|--recursive)',
    r'(?:^|[;&|\s])(mkfs|mkswap|fdisk|parted)\s+',
    r'(?:^|[;&|\s])dd\s+.*if=',
    r'(?:^|[;&|\s])(reboot|shutdown|poweroff)',
    r':\(\)\{\s*:\s*\|\s*:\s*&\s*\}\s*;',  # Fork Bomb!
]
```

**改进空间**: 这些AI能力目前都是**被动触发**(用户点击按钮)，尚未与实时监控形成**主动联动**(即异常自动触发AI分析)。

---

## 3. 能力成熟度评估矩阵

### 3.1 CMMI风格评级

```
Level 5 (优化级) ████████████████████████  100%
Level 4 (管理级) ████████████████░░░░░░░░   70%
Level 3 (定义级) ██████████░░░░░░░░░░░░░░   40%
Level 2 (可重复级) ████░░░░░░░░░░░░░░░░░░░   20%  ← 当前位置
Level 1 (初始级) ░░░░░░░░░░░░░░░░░░░░░░░░░    0%
```

### 3.2 各维度详细评分 (满分10分)

| 维度 | 得分 | 说明 |
|------|------|------|
| **数据采集完整性** | 6/10 | 基础指标齐全，缺自定义/标签/元数据 |
| **数据采集可靠性** | 5/10 | 有双模式兜底，缺降级/自愈/质量校验 |
| **数据存储性能** | 3/10 | SQLite不适合时序数据，需TSDB |
| **规则引擎灵活性** | 1/10 | 仅SSL硬编码阈值，无可配置规则 |
| **异常检测智能化** | 0/10 | 完全空白，无任何自动检测 |
| **告警通知覆盖度** | 3/10 | 2个渠道，无路由/聚合/升级 |
| **告警管理闭环** | 1/10 | 无确认/静默/历史/统计 |
| **可视化丰富度** | 4/10 | 基础图表，缺高级交互 |
| **AI融合深度** | 7/10 | AI能力强但未与监控联动 |
| **可配置性** | 2/10 | 大量硬编码，UI配置入口少 |
| **可扩展性** | 4/10 | Django架构良好，但监控模块耦合紧 |
| **高可用设计** | 3/10 | 单点采集，无HA/灾备 |
| **综合得分** | **3.4/10** | **处于"原型验证"向"生产可用"过渡阶段** |

---

## 4. 行业最佳实践对比

### 4.1 主流开源方案对标

| 方案 | 定位 | 规则引擎 | 异常检测 | 可视化 | 适用规模 | 与AiOps契合度 |
|------|------|---------|---------|--------|---------|-------------|
| **Prometheus + Alertmanager** | 云原生标准 | PromQL强大 | 基础Recording Rules | Grafana生态 | 中大型 | ⭐⭐⭐⭐⭐ 推荐 |
| **Zabbix** | 企业级全功能 | 触发器+表达式 | 基础趋势预测 | 内置Dashboard | 大型 | ⭐⭐⭐⭐ 重 |
| **VictoriaMetrics** | 高性能TSDB | 兼容PromQL | VM Alert内置 | Grafana | 超大规模 | ⭐⭐⭐⭐⭐ |
| **Datadog/Sentry** | SaaS商业 | APM深度集成 | ML异常检测 | 商业级UI | 全规模 | ⭐⭐⭐ 成本高 |
| **Grafana Loki** | 日志监控 | LogQL | 基础 | Grafana统一 | 中大型 | ⭐⭐⭐⭐ 补充 |
| **夜莺(Victoriametrics)** | 国产Prometheus增强 | 告警规则+屏蔽 | 基础 | 自带UI | 中大型 | ⭐⭐⭐⭐⭐ |
| **OpenMonitor** | 轻量级 | 简单阈值 | 无 | 基础 | 小型 | ⭐⭐ 太轻量 |

### 4.2 推荐技术选型: Prometheus + 自研规则引擎

基于 AiOps 项目特点(Django技术栈 + AI能力 + 中小规模起步)，推荐混合方案:

```
┌─────────────────────────────────────────────────────────────┐
│                   AiOps 监控架构 (目标)                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │  Agent   │  │  Exporter│  │  PushGW  │  │  Custom  │    │
│  │ (现有)   │  │ (Node)   │  │ (新增)   │  │ Metrics  │    │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
│       │             │             │             │           │
│       ▼             ▼             ▼             ▼           │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Prometheus TSDB                         │   │
│  │         (时序数据存储 + PromQL查询引擎)               │   │
│  └──────────────────────┬──────────────────────────────┘   │
│                         │                                   │
│       ┌─────────────────┼─────────────────┐               │
│       ▼                 ▼                 ▼               │
│  ┌──────────┐   ┌──────────────┐   ┌──────────────┐      │
│  │ AlertMgr │◀──│  AiOps Rule  │──▶│ Notification │      │
│  │ (可选)   │   │   Engine     │   │   Center     │      │
│  └──────────┘   │  (自研Django)│   │  (多渠道)    │      │
│                 └──────┬───────┘   └──────┬───────┘      │
│                        │                   │              │
│                        ▼                   ▼              │
│                 ┌──────────┐         ┌──────────┐         │
│                 │ Anomaly  │         │ DingTalk │         │
│                 │ Detector │         │ WeChat   │         │
│                 │ (ML/AI)  │         │ Email    │         │
│                 └──────────┘         │ SMS ...  │         │
│                                      └──────────┘         │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Grafana Visualization                   │   │
│  │    (Dashboard + Alert Annotation + Explore)          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. 落地实施方案 - 架构设计

### 5.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AiOps 智能监控平台 v2.0                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌────────────────── 表示层 (Presentation) ──────────────────────────┐  │
│  │                                                                     │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │ Dashboard│  │ Alert    │  │ Rule     │  │ Grafana (Embedded)│  │  │
│  │  │ (实时)   │  │ Center   │  │ Config   │  │ (高级分析)        │  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │  │
│  └──────────────────────────┬──────────────────────────────────────┘  │
│                             │                                         │
│  ┌──────────────────────────▼──────────────────────────────────────┐  │
│  │                    应用层 (Application)                          │  │
│  │                                                                     │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────┐  │  │
│  │  │ Rule Engine│ │ Anomaly    │ │ Alert      │ │ Notification │  │  │
│  │  │ (DSL解析)  │ │ Detection  │ │ Aggregator │ │ Router       │  │  │
│  │  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └──────┬───────┘  │  │
│  │        │              │             │               │           │  │
│  │  ┌─────▼──────────────▼─────────────▼───────────────▼───────┐   │  │
│  │  │              Celery Beat Scheduler                     │   │  │
│  │  │         (规则评估调度 / 任务编排)                       │   │  │
│  │  └───────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────┬──────────────────────────────────────┘  │
│                             │                                         │
│  ┌──────────────────────────▼──────────────────────────────────────┐  │
│  │                    数据层 (Data)                                 │  │
│  │                                                                     │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐  │  │
│  │  │ PostgreSQL │  │ Redis      │  │ Prometheus │  │ InfluxDB  │  │  │
│  │  │ (业务数据) │  │ (缓存/队列)│  │ (实时指标) │  │ (长期归档)│  │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └───────────┘  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
│  ┌────────────────── 采集层 (Collection) ────────────────────────────┐  │
│  │                                                                     │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │  │
│  │  │ Host     │  │ K8s      │  │ Cloud    │  │ Custom Push      │  │  │
│  │  │ Agent    │  │ Collector│  │ Sync     │  │ Gateway          │  │  │
│  │  │ (现有)   │  │ (现有)   │  │ (现有)   │  │ (HTTP API)       │  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 技术栈选型

| 层次 | 技术 | 版本 | 用途 |
|------|------|------|------|
| **时序数据库** | Prometheus | 2.51+ | 实时指标存储 & 查询 |
| **长期归档** | Victoria Metrics / TimescaleDB | 1.x / PG插件 | 历史数据低成本存储 |
| **可视化** | Grafana | 11.x | 仪表盘 & 探索分析 |
| **规则引擎** | Django自研 + Celery | 5.x / 5.x | 规则定义 & 评估调度 |
| **消息队列** | Redis (已有) | 7.x | 告警事件队列 |
| **异常检测** | scikit-learn + statsmodels | 1.x / 0.14 | 统计 & ML算法 |
| **通知渠道** | requests + SDK | - | 多渠道API调用 |
| **前端框架** | Vue3 + ECharts / Apache ECharts | 3.x / 5.x | 实时图表渲染 |

---

## 6. 核心模块一：可配置预警规则引擎

### 6.1 规则数据模型

```python
# monitoring/models.py

from django.db import models
from django.contrib.auth.models import User
import json


class AlertRule(models.Model):
    """
    预警规则定义
    支持: 静态阈值 / 动态基线 / 复合条件 / 周期检测
    """
    
    SEVERITY_CHOICES = [
        ('P0', '致命 (Critical)'),
        ('P1', '严重 (Major)'),
        ('P2', '警告 (Warning)'),
        ('P3', '提示 (Info)'),
    ]
    
    STATUS_CHOICES = [
        ('enabled', '启用'),
        ('disabled', '禁用'),
        ('draft', '草稿'),
    ]
    
    RULE_TYPE_CHOICES = [
        ('threshold', '静态阈值'),       # cpu_usage > 90
        ('baseline', '动态基线'),        # cpu_usage > baseline * 1.5
        ('trend', '趋势检测'),           # memory 持续上升 3 个周期
        ('composite', '复合条件'),        # (cpu > 80) AND (mem > 85)
        ('absence', '消失检测'),          # heartbeat 丢失 > 5min
        ('anomaly', '异常检测'),          # ML 自动检测
    ]
    
    # === 基本信息 ===
    name = models.CharField("规则名称", max_length=200, unique=True)
    description = models.TextField("规则描述", blank=True)
    rule_type = models.CharField("规则类型", max_length=20, choices=RULE_TYPE_CHOICES, default='threshold')
    severity = models.CharField("严重级别", max_length=10, choices=SEVERITY_CHOICES, default='P1')
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='enabled')
    
    # === 目标范围 ===
    target_servers = models.ManyToManyField(
        'cmdb.Server', 
        verbose_name="目标服务器",
        blank=True,
        related_name='alert_rules'
    )
    target_groups = models.ManyToManyField(
        'cmdb.ServerGroup',
        verbose_name="目标分组",
        blank=True,
        related_name='alert_rules'
    )
    target_all = models.BooleanField("应用于所有服务器", default=False)
    
    # === 指标配置 ===
    metric_name = models.CharField("监控指标", max_length=50,
        help_text="cpu_usage/mem_usage/disk_usage/load_1min/net_in/net_out")
    
    # === 条件表达式 (JSON) ===
    condition_config = models.JSONField("条件配置", default=dict,
        help_text="""
        静态阈值示例: {"operator": "gt", "value": 90, "unit": "%"}
        动态基线示例: {"operator": "gt", "baseline_type": "avg_7d", "multiplier": 1.5}
        复合条件示例: {"logic": "AND", "conditions": [...]}
        趋势检测示例: {"direction": "up", "window": 3, "threshold": 5}
        """)
    
    # === 检测周期 ===
    evaluate_interval = models.PositiveIntegerField("评估间隔(秒)", default=60,
        help_text="多久评估一次该规则")
    lookback_window = models.PositiveIntegerField("回溯窗口(个)", default=5,
        help_text="取最近N个数据点进行判断")
    
    # === 告警控制 ===
    cooldown_seconds = models.PositiveIntegerField("冷却时间(秒)", default=300,
        help_text="同一目标触发后，N秒内不再重复触发")
    max_alerts_per_hour = models.PositiveIntegerField("每小时最大告警数", default=10,
        help_text="防告警风暴限制")
    
    # === 通知配置 ===
    notify_channels = models.JSONField("通知渠道", default=list,
        help_text="['dingtalk', 'wechat', 'email', 'sms']")
    notify_users = models.ManyToManyField(User, verbose_name="通知人员", blank=True)
    notify_template = models.TextField("通知模板", default="", blank=True)
    
    # === 元数据 ===
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_triggered_at = models.DateTimeField("最后触发时间", null=True, blank=True)
    trigger_count = models.PositiveIntegerField("累计触发次数", default=0)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'rule_type']),
            models.Index(fields=['severity']),
        ]
    
    def __str__(self):
        return f"[{self.severity}] {self.name}"


class AlertEvent(models.Model):
    """告警事件实例 (每次触发产生一条)"""
    
    STATUS_CHOICES = [
        ('firing', '触发中'),
        ('resolved', '已恢复'),
        ('acknowledged', '已确认'),
        ('silenced', '已静默'),
    ]
    
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='events')
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True, related_name='alert_events')
    
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='firing')
    severity = models.CharField("级别", max_length=10)
    
    # 告警内容
    metric_name = models.CharField("指标名", max_length=50)
    current_value = models.FloatField("当前值")
    threshold_value = models.FloatField("阈值/基线", null=True, blank=True)
    message = models.TextField("告警消息", default="")
    detail = models.JSONField("详细信息", default=dict)
    
    # 生命周期
    fired_at = models.DateTimeField("触发时间", auto_now_add=True)
    resolved_at = models.DateTimeField("恢复时间", null=True, blank=True)
    acknowledged_at = models.DateTimeField("确认时间", null=True, blank=True)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    # 通知追踪
    notification_log = models.JSONField("通知记录", default=list,
        help_text="[{'channel':'dingtalk','status':'sent','at':'...'}, ...]")
    
    class Meta:
        ordering = ['-fired_at']
        indexes = [
            models.Index(fields=['status', '-fired_at']),
            models.Index(fields=['server', 'status']),
        ]
    
    @property
    def duration(self):
        """告警持续时间"""
        end = self.resolved_at or timezone.now()
        return (end - self.fired_at).total_seconds()


class AlertSilenceRule(models.Model):
    """告警静默规则 (维护窗口)"""
    
    name = models.CharField("静默名称", max_length=200)
    
    # 匹配条件
    match_severity = models.CharField("匹配级别", max_length=10, blank=True)
    match_rule_name = models.CharField("匹配规则", max_length=200, blank=True)
    match_server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True, blank=True)
    
    # 时间范围
    start_time = models.DateTimeField("开始时间")
    end_time = models.DateTimeField("结束时间")
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    comment = models.TextField("备注", blank=True)
    is_active = models.BooleanField("生效中", default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)


class AlertEscalationPolicy(models.Model):
    """告警升级策略"""
    
    name = models.CharField("策略名称", max_length=200)
    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='escalations')
    
    levels = models.JSONField("升级层级", default=list,
        help_text="""
        [
            {"level": 1, "delay_min": 0, "channels": ["dingtalk"], "users": ["oncall_primary"]},
            {"level": 2, "delay_min": 15, "channels": ["dingtalk","sms"], "users": ["oncall_manager"]},
            {"level": 3, "delay_min": 60, "channels": ["dingtalk","sms","phone"], "users": ["team_lead"]},
        ]
        """)
    
    is_active = models.BooleanField(default=True)
```

### 6.2 规则引擎核心逻辑

```python
# monitoring/engine/rule_evaluator.py

"""
AiOps 预警规则引擎
支持多种规则类型的评估与触发
"""

import logging
import statistics
from datetime import datetime, timedelta
from django.utils import timezone
from django.db import connection
from monitoring.models import AlertRule, AlertEvent, AlertSilenceRule

logger = logging.getLogger(__name__)


class RuleEvaluator:
    """规则评估器"""
    
    def __init__(self, rule: AlertRule):
        self.rule = rule
        self.condition = rule.condition_config
    
    def evaluate(self, server_id=None):
        """
        评估规则是否触发
        
        Returns:
            (should_fire: bool, detail: dict)
        """
        # 1. 获取目标服务器列表
        servers = self._get_target_servers(server_id)
        if not servers:
            return False, {'reason': 'no_target_servers'}
        
        results = []
        for server in servers:
            result = self._evaluate_single_server(server)
            results.append(result)
            
            if result['triggered']:
                self._fire_alert(server, result)
        
        triggered_count = sum(1 for r in results if r['triggered'])
        return triggered_count > 0, {
            'evaluated_servers': len(servers),
            'triggered_servers': triggered_count,
            'results': results
        }
    
    def _get_target_servers(self, server_id=None):
        """获取规则适用的服务器列表"""
        from cmdb.models import Server
        
        if server_id:
            return Server.objects.filter(id=server_id, status='Running')
        
        if self.rule.target_all:
            return Server.objects.filter(status='Running')
        
        qs = Server.objects.filter(status='Running')
        if self.rule.target_servers.exists():
            qs = qs.filter(id__in=self.rule.target_servers.values_list('id', flat=True))
        if self.rule.target_groups.exists():
            qs = qs.filter(group_id__in=self.rule.target_groups.values_list('id', flat=True))
        return qs.distinct()
    
    def _get_metric_data(self, server, window=5):
        """获取服务器的指标历史数据"""
        from cmdb.models import ServerMetric
        
        metrics = ServerMetric.objects.filter(
            server=server,
            metric_name=self.rule.metric_name  # 需要扩展模型或映射
        ).order_by('-created_at')[:window]
        
        return list(metrics)
    
    def _evaluate_single_server(self, server):
        """对单个服务器评估规则"""
        handler_map = {
            'threshold': self._eval_threshold,
            'baseline': self._eval_baseline,
            'trend': self._eval_trend,
            'composite': self._eval_composite,
            'absence': self._eval_absence,
            'anomaly': self._eval_anomaly,
        }
        
        handler = handler_map.get(self.rule.rule_type)
        if not handler:
            return {'server_id': server.id, 'triggered': False, 
                    'reason': f'unknown_rule_type: {self.rule.rule_type}'}
        
        return handler(server)
    
    def _eval_threshold(self, server):
        """静态阈值评估: cpu_usage > 90"""
        data = self._get_metric_data(server, window=1)
        if not data:
            return {'server_id': server.id, 'triggered': False, 'reason': 'no_data'}
        
        latest = data[0]
        value = getattr(latest, self._metric_to_field(), 0)
        
        op = self.condition.get('operator', 'gt')
        threshold = self.condition.get('value', 0)
        
        triggered = self._compare(value, op, threshold)
        
        return {
            'server_id': server.id,
            'triggered': triggered,
            'current_value': value,
            'threshold': threshold,
            'metric': self.rule.metric_name,
        }
    
    def _eval_baseline(self, server):
        """动态基线评估: 当前值 > 历史基线 * 倍数"""
        window = self.condition.get('lookback_hours', 168)  # 默认7天
        multiplier = self.condition.get('multiplier', 1.5)
        baseline_type = self.condition.get('baseline_type', 'avg')  # avg/p95/p99
        
        now = timezone.now()
        start = now - timedelta(hours=window)
        
        # 从 Prometheus 或 DB 获取历史基线
        historical = self._get_historical_stats(server, start, now, baseline_type)
        if not historical:
            return {'server_id': server.id, 'triggered': False, 'reason': 'insufficient_history'}
        
        current_data = self._get_metric_data(server, window=1)
        if not current_data:
            return {'server_id': server.id, 'triggered': False, 'reason': 'no_current_data'}
        
        current_val = getattr(current_data[0], self._metric_to_field(), 0)
        baseline_val = historical * multiplier
        
        triggered = current_val > baseline_val
        
        return {
            'server_id': server.id,
            'triggered': triggered,
            'current_value': current_val,
            'baseline': baseline_val,
            'multiplier': multiplier,
        }
    
    def _eval_trend(self, server):
        """趋势检测: 指标连续N个周期朝同一方向变化"""
        window = self.condition.get('window', 5)
        direction = self.condition.get('direction', 'up')  # up/down
        change_threshold = self.condition.get('change_threshold', 1)  # 最小变化幅度
        
        data = self._get_metric_data(server, window=window)
        if len(data) < window:
            return {'server_id': server.id, 'triggered': False, 'reason': 'insufficient_data'}
        
        values = [getattr(d, self._metric_to_field()) for d in reversed(data)]
        
        # 计算连续变化方向
        changes = []
        for i in range(1, len(values)):
            diff = values[i] - values[i-1]
            changes.append(diff)
        
        # 检查是否连续同方向且超过阈值
        consistent_direction = all(
            (c > change_threshold if direction == 'up' else c < -change_threshold)
            for c in changes
        )
        
        trend_slope = (values[-1] - values[0]) / len(values) if len(values) > 1 else 0
        
        return {
            'server_id': server.id,
            'triggered': consistent_direction,
            'trend_direction': direction,
            'slope': round(trend_slope, 4),
            'values': values,
        }
    
    def _eval_composite(self, server):
        """复合条件: (cpu > 80) AND (mem > 85)"""
        logic = self.condition.get('logic', 'AND')
        sub_conditions = self.condition.get('conditions', [])
        
        sub_results = []
        for sub_cond in sub_conditions:
            # 递归评估子条件 (简化处理)
            metric = sub_cond.get('metric')
            operator = sub_cond.get('operator')
            value = sub_cond.get('value')
            
            data = self._get_metric_data(server, window=1)
            if data:
                actual = getattr(data[0], self._metric_name_to_field(metric), 0)
                sub_results.append(self._compare(actual, operator, value))
            else:
                sub_results.append(False)
        
        if logic == 'AND':
            triggered = all(sub_results)
        else:  # OR
            triggered = any(sub_results)
        
        return {
            'server_id': server.id,
            'triggered': triggered,
            'sub_results': sub_results,
            'logic': logic,
        }
    
    def _eval_absence(self, server):
        """心跳消失检测: N分钟内无数据上报"""
        absent_minutes = self.condition.get('absent_minutes', 5)
        
        last_metric = self._get_metric_data(server, window=1)
        if not last_metric:
            return {'server_id': server.id, 'triggered': True, 
                    'reason': 'never_reported'}
        
        elapsed = (timezone.now() - last_metric[0].created_at).total_seconds() / 60
        
        return {
            'server_id': server.id,
            'triggered': elapsed > absent_minutes,
            'last_report_minutes_ago': round(elapsed, 1),
            'threshold_minutes': absent_minutes,
        }
    
    def _eval_anomaly(self, server):
        """ML异常检测 (委托给 anomaly detector)"""
        from .anomaly_detector import AnomalyDetector
        
        detector = AnomalyDetector()
        data = self._get_metric_data(server, window=30)
        
        if len(data) < 10:
            return {'server_id': server.id, 'triggered': False, 'reason': 'insufficient_for_ml'}
        
        values = [getattr(d, self._metric_to_field()) for d in reversed(data)]
        is_anomaly, score, reason = detector.detect(values)
        
        return {
            'server_id': server.id,
            'triggered': is_anomaly,
            'anomaly_score': score,
            'method': detector.method_used,
            'reason': reason,
        }
    
    def _fire_alert(self, server, eval_result):
        """触发告警 (含冷却检查和静默检查)"""
        # 1. 冷却检查
        recent_alert = AlertEvent.objects.filter(
            rule=self.rule,
            server=server,
            status='firing',
            fired_at__gte=timezone.now() - timedelta(seconds=self.rule.cooldown_seconds)
        ).exists()
        
        if recent_alert:
            logger.info(f"Cooldown active for rule {self.rule.name} on server {server.hostname}")
            return
        
        # 2. 静默检查
        if self._is_silenced(server):
            logger.info(f"Alert silenced for rule {self.rule.name} on server {server.hostname}")
            return
        
        # 3. 创建告警事件
        event = AlertEvent.objects.create(
            rule=self.rule,
            server=server,
            severity=self.rule.severity,
            metric_name=self.rule.metric_name,
            current_value=eval_result.get('current_value', 0),
            threshold_value=eval_result.get('threshold'),
            message=self._format_message(server, eval_result),
            detail=eval_result,
        )
        
        # 4. 更新规则统计
        AlertRule.objects.filter(id=self.rule.id).update(
            last_triggered_at=timezone.now(),
            trigger_count=models.F('trigger_count') + 1
        )
        
        # 5. 发送通知 (异步)
        from .notification import send_alert_notifications
        send_alert_notifications.delay(event.id)
        
        logger.warning(f"🚨 ALERT FIRED: [{self.rule.severity}] {self.rule.name} -> {server.hostname}")
    
    def _is_silenced(self, server):
        """检查是否有活跃的静默规则覆盖此告警"""
        now = timezone.now()
        return AlertSilenceRule.objects.filter(
            is_active=True,
            start_time__lte=now,
            end_time__gte=now
        ).filter(
            models.Q(match_server=server) |
            models.Q(match_server__isnull=True)
        ).filter(
            models.Q(match_severity='') | models.Q(match_severity=self.rule.severity) |
            models.Q(match_severity__isnull=True)
        ).exists()
    
    def _compare(self, actual, operator, expected):
        """比较操作符"""
        ops = {
            'gt': lambda a, b: a > b,
            'gte': lambda a, b: a >= b,
            'lt': lambda a, b: a < b,
            'lte': lambda a, b: a <= b,
            'eq': lambda a, b: abs(a - b) < 0.01,
            'neq': lambda a, b: abs(a - b) >= 0.01,
        }
        fn = ops.get(operator, ops['gt'])
        return fn(actual, expected)
    
    def _metric_to_field(self):
        """指标名到模型字段的映射"""
        mapping = {
            'cpu_usage': 'cpu_usage',
            'mem_usage': 'mem_usage',
            'disk_usage': 'disk_usage',
            'load_1min': 'load_1min',
            'net_in': 'net_in',
            'net_out': 'net_out',
            'disk_read_rate': 'disk_read_rate',
            'disk_write_rate': 'disk_write_rate',
        }
        return mapping.get(self.rule.metric_name, 'cpu_usage')
    
    def _format_message(self, server, result):
        """格式化告警消息"""
        templates = {
            'threshold': f"⚠️ 【{self.rule.name}】{server.hostname} {self.rule.metric_name}={result.get('current_value', '?')} {self.condition.get('operator', '>')} {self.condition.get('value', '?')}",
            'baseline': f"📈 【{self.rule.name}】{server.hostname} {self.rule.metric_name}={result.get('current_value', '?')} 超过动态基线 ({result.get('baseline', '?')} × {self.condition.get('multiplier', '?')})",
            'trend': f"📊 【{self.rule.name}】{server.hostname} {self.rule.metric_name} 持续{self.condition.get('direction', 'up')}趋势 (斜率={result.get('slope', '?')})",
            'composite': f"🔗 【{self.rule.name}】{server.hostname} 复合条件触发 ({self.condition.get('logic', 'AND')})",
            'absence': f"❌ 【{self.rule.name}】{server.hostname} 已 {result.get('last_report_minutes_ago', '?')} 分钟未上报数据",
            'anomaly': f"🤖 【{self.rule.name}】{server.hostname} {self.rule.metric_name} 检测到异常 (分数={result.get('anomaly_score', '?')})",
        }
        return templates.get(self.rule.rule_type, f"【{self.rule.name}】{server.hostname} 告警")
    
    def _get_historical_stats(self, server, start, end, stat_type='avg'):
        """获取历史统计数据 (从DB或Prometheus)"""
        from cmdb.models import ServerMetric
        field = self._metric_to_field()
        
        metrics = ServerMetric.objects.filter(
            server=server,
            created_at__range=(start, end)
        )
        
        values = [getattr(m, field) for m in metrics]
        
        if not values:
            return None
        
        if stat_type == 'avg':
            return statistics.mean(values)
        elif stat_type == 'p95':
            sorted_vals = sorted(values)
            idx = int(len(sorted_vals) * 0.95)
            return sorted_vals[min(idx, len(sorted_vals)-1)]
        elif stat_type == 'p99':
            sorted_vals = sorted(values)
            idx = int(len(sorted_vals) * 0.99)
            return sorted_vals[min(idx, len(sorted_vals)-1)]
        elif stat_type == 'max':
            return max(values)
        elif stat_type == 'min':
            return min(values)
        
        return statistics.mean(values)
```

---

## 7. 核心模块二：实时数据采集增强

### 7.1 采集架构升级方案

```python
# monitoring/collectors/enhanced_collector.py

"""
增强版数据采集器
新增: 数据质量校验 / 标签体系 / 自定义指标 / 降级策略
"""

import time
import logging
import threading
from collections import deque
from datetime import datetime
from django.db import connections
from django.conf import settings
from prometheus_client import CollectorRegistry, Gauge, Counter, Histogram
import requests

logger = logging.getLogger(__name__)


class MetricPoint:
    """单个数据点 (带标签)"""
    def __init__(self, name, value, timestamp=None, tags=None, hostname=''):
        self.name = name
        self.value = value
        self.timestamp = timestamp or time.time()
        self.tags = tags or {}
        self.hostname = hostname
    
    def to_prometheus_format(self):
        """转换为 Prometheus 格式"""
        label_str = ','.join(f'{k}="{v}"' for k,v in self.tags.items())
        return f'{self.name}{{{label_str}}} {self.value} {int(self.timestamp*1000)}'


class DataQualityChecker:
    """数据质量校验器"""
    
    VALIDATION_RULES = {
        'cpu_usage': {'min': 0, 'max': 400},   # 多核可能>100%
        'mem_usage': {'min': 0, 'max': 100},
        'disk_usage': {'min': 0, 'max': 100},
        'load_1min': {'min': 0, 'max': 1000},
        'net_in': {'min': 0, 'max': 10_000_000},  # KB/s 上限
        'net_out': {'min': 0, 'max': 10_000_000},
        'disk_read_rate': {'min': 0, 'max': 1_000_000},
        'disk_write_rate': {'min': 0, 'max': 1_000_000},
    }
    
    @classmethod
    def validate(cls, metric_name, value):
        """校验单个指标值"""
        rules = cls.VALIDATION_RULES.get(metric_name)
        if not rules:
            return True, None  # 未知指标放行
        
        if value < rules['min'] or value > rules['max']:
            return False, f"value {value} out of range [{rules['min']}, {rules['max']}]"
        
        # NaN/Inf 检查
        import math
        if math.isnan(value) or math.isinf(value):
            return False, f"invalid numeric value: {value}"
        
        return True, None
    
    @classmethod
    def sanitize(cls, metric_name, value):
        """清洗异常值 (截断到合法范围)"""
        rules = cls.VALIDATION_RULES.get(metric_name)
        if not rules:
            return value
        
        return max(rules['min'], min(rules['max'], value))


class EnhancedCollector:
    """增强版采集器"""
    
    def __init__(self):
        self.registry = CollectorRegistry()
        self.metrics_cache = {}  # server_id -> 最近N个数据点
        self.collection_stats = {
            'total_collections': 0,
            'success_count': 0,
            'failure_count': 0,
            'quality_rejects': 0,
        }
        self._lock = threading.Lock()
        
        # Prometheus 导出指标
        self.prom_metrics = {
            'collection_latency': Histogram(
                'aiops_collection_duration_seconds',
                'Time spent collecting metrics',
                ['mode'], registry=self.registry
            ),
            'collection_success': Counter(
                'aiops_collection_success_total',
                'Total successful collections',
                ['mode', 'server_id'], registry=self.registry
            ),
            'collection_errors': Counter(
                'aiops_collection_errors_total',
                'Total collection errors',
                ['mode', 'error_type'], registry=self.registry
            ),
        }
    
    def collect_server(self, server):
        """采集单台服务器 (增强版)"""
        start_time = time.time()
        mode = 'agent' if server.use_agent else 'ssh'
        
        try:
            raw_data = self._raw_collect(server, mode)
            
            # 数据质量校验
            clean_data = {}
            quality_issues = []
            
            for key, value in raw_data.items():
                valid, issue = DataQualityChecker.validate(key, value)
                if valid:
                    clean_data[key] = value
                else:
                    clean_data[key] = DataQualityChecker.sanitize(key, value)
                    quality_issues.append(f"{key}: {issue}")
                    with self._lock:
                        self.collection_stats['quality_rejects'] += 1
            
            # 添加标签
            tags = {
                'hostname': server.hostname,
                'ip': str(server.ip_address),
                'os': server.os_name,
                'provider': server.provider,
                'group': server.group.name if server.group else 'ungrouped',
                'env': 'production',  # 可从配置读取
                'collection_mode': mode,
            }
            
            # 创建 MetricPoint 列表
            points = [
                MetricPoint(f'aiops_{k}', v, tags=tags, hostname=server.hostname)
                for k, v in clean_data.items()
            ]
            
            # 存入缓存 (用于异常检测)
            self._update_cache(server.id, points)
            
            # 写入数据库
            self._persist(server, clean_data)
            
            # 更新统计
            with self._lock:
                self.collection_stats['total_collections'] += 1
                self.collection_stats['success_count'] += 1
            
            latency = time.time() - start_time
            self.prom_metrics['collection_latency'].labels(mode=mode).observe(latency)
            self.prom_metrics['collection_success'].labels(mode=mode, server_id=str(server.id)).inc()
            
            return {
                'success': True,
                'server_id': server.id,
                'hostname': server.hostname,
                'metrics': clean_data,
                'quality_issues': quality_issues,
                'latency_ms': round(latency * 1000, 2),
            }
            
        except Exception as e:
            with self._lock:
                self.collection_stats['total_collections'] += 1
                self.collection_stats['failure_count'] += 1
            
            self.prom_metrics['collection_errors'].labels(mode=mode, error_type=type(e).__name__).inc()
            logger.error(f"[Collect Error] {server.hostname}: {e}")
            
            return {
                'success': False,
                'server_id': server.id,
                'hostname': server.hostname,
                'error': str(e),
            }
    
    def _raw_collect(self, server, mode):
        """原始数据采集 (Agent 或 SSH)"""
        if mode == 'agent':
            return self._collect_via_agent(server)
        else:
            return self._collect_via_ssh(server)
    
    def _collect_via_agent(self, server):
        """通过 Agent HTTP 接口采集"""
        agent_url = f"http://{server.ip_address}:10050/metrics"
        resp = requests.get(agent_url, timeout=5)
        resp.raise_for_status()
        return resp.json()
    
    def _collect_via_ssh(self, server):
        """通过 SSH 采集 (复用现有逻辑)"""
        # 这里可以引用现有的 run_agent.py 中的 SSH 采集逻辑
        # 为保持简洁，此处省略具体实现
        pass
    
    def _update_cache(self, server_id, points):
        """更新本地缓存 (保留最近100个点用于异常检测)"""
        if server_id not in self.metrics_cache:
            self.metrics_cache[server_id] = deque(maxlen=100)
        
        for p in points:
            self.metrics_cache[server_id].append({
                'name': p.name,
                'value': p.value,
                'timestamp': p.timestamp,
                'tags': p.tags,
            })
    
    def _persist(self, server, data):
        """持久化到数据库"""
        from cmdb.models import ServerMetric
        connections.close_all()  # 防止 Gone Away
        
        ServerMetric.objects.create(
            server=server,
            cpu_usage=round(data.get('cpu', 0), 1),
            mem_usage=round(data.get('mem', 0), 1),
            disk_usage=round(data.get('disk', 0), 1),
            load_1min=data.get('load', 0),
            net_in=data.get('net_in', 0),
            net_out=data.get('net_out', 0),
            disk_read_rate=data.get('disk_read', 0),
            disk_write_rate=data.get('disk_write', 0),
        )
    
    def get_cached_series(self, server_id, metric_name, limit=50):
        """获取缓存的时序数据 (供异常检测使用)"""
        cache = self.metrics_cache.get(server_id, deque())
        full_name = f'aiops_{metric_name}'
        
        return [
            {'timestamp': p['timestamp'], 'value': p['value']}
            for p in cache
            if p['name'] == full_name
        ][-limit:]
    
    def get_stats(self):
        """获取采集统计信息"""
        with self._lock:
            return dict(self.collection_stats)
    
    def expose_metrics(self):
        """暴露 Prometheus 格式的指标 (用于 /metrics 端点)"""
        from prometheus_client import generate_latest
        return generate_latest(self.registry)
```

---

## 8. 核心模块三：异常检测算法库

### 8.1 算法选型与实现

```python
# monitoring/anomaly_detector.py

"""
AiOps 异常检测算法库
提供多种检测方法: 统计基线 / Z-Score / IQR / Isolation Forest / LSTM预测
"""

import numpy as np
import statistics
from typing import Tuple, List, Optional
from dataclasses import dataclass


@dataclass
class AnomalyResult:
    """异常检测结果"""
    is_anomaly: bool
    score: float  # 0-1, 越大越异常
    method: str
    reason: str
    details: dict = None


class BaseDetector:
    """检测器基类"""
    
    method_name = "base"
    
    def detect(self, series: List[float]) -> AnomalyResult:
        if len(series) < self.window:
            return AnomalyResult(False, 0, self.method_name, "insufficient_data")
        
        # 使用历史窗口计算均值和标准差
        historical = series[-(self.window+1):-1]  # 排除最新值
        mean = statistics.mean(historical)
        std = statistics.stdev(historical) if len(historical) > 1 else 0
        
        latest = series[-1]
        z = self._z_score(latest, mean, std)
        
        is_anomaly = z > self.threshold
        score = min(1.0, z / (self.threshold * 2))
        
        return AnomalyResult(
            is_anomaly, score, self.method_name,
            f"Z-Score={z:.2f} (threshold={self.threshold}, μ={mean:.2f}, σ={std:.2f})",
            {'z_score': round(z, 3), 'mean': round(mean, 3), 'std': round(std, 3)}
        )


class IQRDetector(BaseDetector):
    """IQR 四分位距检测器 (抗离群点干扰，适合非正态分布)"""
    
    method_name = "iqr"
    
    def __init__(self, k=1.5, window=30):
        self.k = k
        self.window = window
    
    def detect(self, series: List[float]) -> AnomalyResult:
        if len(series) < self.window:
            return AnomalyResult(False, 0, self.method_name, "insufficient_data")
        
        historical = sorted(series[-(self.window+1):-1])
        n = len(historical)
        
        q1 = historical[n // 4]
        q3 = historical[3 * n // 4]
        iqr = q3 - q1
        
        lower_bound = q1 - self.k * iqr
        upper_bound = q3 + self.k * iqr
        
        latest = series[-1]
        
        if latest < lower_bound:
            score = min(1.0, (lower_bound - latest) / iqr)
            return AnomalyResult(True, score, self.method_name,
                f"值 {latest:.2f} 低于IQR下界 {lower_bound:.2f}", 
                {'direction': 'low', 'q1': q1, 'q3': q3, 'iqr': iqr})
        elif latest > upper_bound:
            score = min(1.0, (latest - upper_bound) / iqr)
            return AnomalyResult(True, score, self.method_name,
                f"值 {latest:.2f} 超过IQR上界 {upper_bound:.2f}",
                {'direction': 'high', 'q1': q1, 'q3': q3, 'iqr': iqr})
        
        return AnomalyResult(False, 0, self.method_name, "normal",
            {'q1': q1, 'q3': q3, 'iqr': iqr})


class MovingAverageDetector(BaseDetector):
    """滑动平均偏差检测器 (适合趋势性数据)"""
    
    method_name = "moving_average"
    
    def __init__(self, ma_window=10, threshold_factor=2.0):
        self.ma_window = ma_window
        self.threshold_factor = threshold_factor
    
    def detect(self, series: List[float]) -> AnomalyResult:
        if len(series) < self.ma_window + 1:
            return AnomalyResult(False, 0, self.method_name, "insufficient_data")
        
        # 计算移动平均
        ma_values = []
        for i in range(self.ma_window, len(series)):
            window = series[i - self.ma_window:i]
            ma_values.append(statistics.mean(window))
        
        latest_actual = series[-1]
        latest_ma = ma_values[-1]
        
        # 计算 MA 残差的标准差
        residuals = [series[self.ma_window + i] - ma_values[i] for i in range(len(ma_values))]
        residual_std = statistics.stdev(residuals) if len(residuals) > 1 else 0
        
        deviation = abs(latest_actual - latest_ma)
        threshold = self.threshold_factor * residual_std if residual_std > 0 else latest_ma * 0.1
        
        is_anomaly = deviation > threshold
        score = min(1.0, deviation / (threshold * 2)) if threshold > 0 else 0
        
        direction = 'high' if latest_actual > latest_ma else 'low'
        
        return AnomalyResult(
            is_anomaly, score, self.method_name,
            f"偏差={deviation:.2f}, MA={latest_ma:.2f}, 阈值={threshold:.2f}",
            {'ma_value': round(latest_ma, 3), 'deviation': round(deviation, 3),
             'direction': direction}
        )


class RateOfChangeDetector(BaseDetector):
    """变化率检测器 (检测突变/尖峰)"""
    
    method_name = "rate_of_change"
    
    def __init__(self, max_change_pct=50.0, min_samples=5):
        self.max_change_pct = max_change_pct
        self.min_samples = min_samples
    
    def detect(self, series: List[float]) -> AnomalyResult:
        if len(series) < self.min_samples:
            return AnomalyResult(False, 0, self.method_name, "insufficient_data")
        
        prev = series[-2]
        curr = series[-1]
        
        if prev == 0:
            return AnomalyResult(False, 0, self.method_name, "zero_base")
        
        change_pct = abs((curr - prev) / prev) * 100
        is_anomaly = change_pct > self.max_change_pct
        score = min(1.0, change_pct / (self.max_change_pct * 2))
        
        direction = 'spike_up' if curr > prev else 'drop_down'
        
        return AnomalyResult(
            is_anomaly, score, self.method_name,
            f"变化率={change_pct:.1f}% (阈值={self.max_change_pct}%)",
            {'prev': round(prev, 3), 'curr': round(curr, 3),
             'change_pct': round(change_pct, 2), 'direction': direction}
        )


class CompositeAnomalyDetector(BaseDetector):
    """
    组合检测器 (投票机制)
    同时运行多种算法，综合判断是否异常
    """
    
    method_name = "composite"
    
    def __init__(self, detectors=None, vote_threshold=0.5, weight_mode='equal'):
        """
        Args:
            detectors: 检测器列表
            vote_threshold: 投票通过率 (0-1), 超过此比例认为异常
            weight_mode: 'equal'(等权) / 'score'(加权平均分数)
        """
        self.detectors = detectors or [
            ZScoreDetector(threshold=2.5),
            IQRDetector(k=1.5),
            MovingAverageDetector(ma_window=10),
            RateOfChangeDetector(max_change_pct=100),
        ]
        self.vote_threshold = vote_threshold
        self.weight_mode = weight_mode
    
    def detect(self, series: List[float]) -> AnomalyResult:
        results = []
        for detector in self.detectors:
            try:
                result = detector.detect(series)
                results.append(result)
            except Exception as e:
                results.append(AnomalyResult(False, 0, detector.method_name, str(e)))
        
        anomaly_count = sum(1 for r in results if r.is_anomaly)
        total = len(results)
        vote_ratio = anomaly_count / total if total > 0 else 0
        
        if self.weight_mode == 'score':
            avg_score = statistics.mean(r.score for r in results)
            final_score = avg_score
        else:
            final_score = vote_ratio
        
        is_anomaly = vote_ratio >= self.vote_threshold
        
        detail_results = [
            {"method": r.method, "anomaly": r.is_anomaly, "score": round(r.score, 3)}
            for r in results
        ]
        
        return AnomalyResult(
            is_anomaly, round(final_score, 4), self.method_name,
            f"{anomaly_count}/{total} 算法判定异常 (阈值={self.vote_threshold})",
            {'vote_ratio': round(vote_ratio, 3), 'results': detail_results}
        )


class AnomalyDetector:
    """
    异常检测统一入口
    根据数据特征自动选择最佳检测策略
    """
    
    def __init__(self, method='auto'):
        self.method = method
        self.method_used = None
    
    def detect(self, values: List[float]) -> Tuple[bool, float, str]:
        """
        检测异常
        
        Args:
            values: 时序数据列表 (越新越靠后)
        
        Returns:
            (is_anomaly, score, reason)
        """
        if len(values) < 5:
            return False, 0.0, "数据量不足(最少5个点)"
        
        # 方法选择
        if self.method == 'auto':
            detector = self._auto_select_detector(values)
        elif self.method == 'zscore':
            detector = ZScoreDetector()
        elif self.method == 'iqr':
            detector = IQRDetector()
        elif self.method == 'composite':
            detector = CompositeAnomalyDetector()
        else:
            detector = ZScoreDetector()
        
        self.method_used = detector.method_name
        result = detector.detect(values)
        
        return result.is_anomaly, result.score, result.reason
    
    def _auto_select_detector(self, values):
        """根据数据特征自动选择检测方法"""
        n = len(values)
        
        # 数据量少 → 用简单方法
        if n < 20:
            return ZScoreDetector(threshold=2.5)
        
        # 检查方差稳定性 (判断是否有明显趋势)
        first_half = values[:n//2]
        second_half = values[n//2:]
        
        var_first = statistics.variance(first_half) if len(first_half) > 1 else 0
        var_second = statistics.variance(second_half) if len(second_half) > 1 else 0
        
        # 方差差异大 → 有趋势或波动变化大，用MA检测
        if var_first > 0 and abs(var_second - var_first) / var_first > 0.5:
            return MovingAverageDetector()
        
        # 默认用组合检测 (最稳健)
        return CompositeAnomalyDetector(vote_threshold=0.6)
```

---

## 9. 核心模块四：智能告警通知中心

### 9.1 通知渠道架构

```python
# monitoring/notification/channel_manager.py

"""
AiOps 多渠道通知中心
支持: 钉钉 / 企业微信 / 邮件 / 短信 / Webhook / Slack / 飞书
"""

import json
import logging
import hashlib
import hmac
import base64
import time
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class NotificationMessage:
    """通知消息标准格式"""
    title: str
    content: str
    severity: str = "P1"
    alert_id: int = 0
    server_name: str = ""
    metric_name: str = ""
    current_value: float = 0.0
    threshold: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    def to_dingtalk_text(self):
        """钉钉文本格式"""
        return f"**{self.title}**\n{self.content}\n\n> 时间: {self.timestamp}"
    
    def to_dingtalk_markdown(self):
        """钉钉Markdown卡片格式"""
        return {
            "msgtype": "markdown",
            "markdown": {
                "title": self.title,
                "text": f"### {self.severity} {self.title}\n\n"
                        f"- **服务器**: {self.server_name}\n"
                        f"- **指标**: {self.metric_name}\n"
                        f"- **当前值**: {self.current_value}\n"
                        f"- **阈值**: {self.threshold}\n\n"
                        f"{self.content}\n\n"
                        f"> {self.timestamp}"
            }
        }
    
    def to_wechat_text(self):
        """企业微信文本格式"""
        return f"<font color=\"warning\">{self.title}</font>\n{self.content}\n\n时间: {self.timestamp}"
    
    def to_email_html(self):
        """邮件HTML格式"""
        severity_colors = {'P0': '#ff4d4f', 'P1': '#fa8c16', 'P2': '#faad14', 'P3': '#52c41a'}
        color = severity_colors.get(self.severity, '#1890ff')
        
        return f"""
        <html>
        <body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; padding: 20px;">
        <div style="max-width: 600px; margin: 0 auto; border: 1px solid #e8e8e8; border-radius: 8px; overflow: hidden;">
            <div style="background: {color}; color: white; padding: 16px 24px;">
                <h2 style="margin: 0;">{self.title}</h2>
                <p style="margin: 4px 0 0; opacity: 0.9;">严重级别: {self.severity}</p>
            </div>
            <div style="padding: 24px;">
                <table style="width: 100%; border-collapse: collapse;">
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><b>服务器</b></td><td>{self.server_name}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><b>监控指标</b></td><td>{self.metric_name}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><b>当前值</b></td><td style="color:{color};font-weight:bold;">{self.current_value}</td></tr>
                    <tr><td style="padding: 8px; border-bottom: 1px solid #eee;"><b>阈值</b></td><td>{self.threshold}</td></tr>
                    <tr><td style="padding: 8px;"><b>触发时间</b></td><td>{self.timestamp}</td></tr>
                </table>
                <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
                <p style="color:#666;line-height:1.6;">{self.content}</p>
            </div>
            <div style="background:#fafafa;padding:12px 24px;font-size:12px;color:#999;text-align:center;">
                AiOps 智能运维平台自动发送 | 请勿直接回复此邮件
            </div>
        </div>
        </body>
        </html>
        """
    
    def to_slack_attachment(self):
        """Slack Attachment 格式"""
        severity_emoji = {'P0': ':rotating_light:', 'P1': ':warning:', 'P2': ':information_source:', 'P3': ':bell:'}
        return {
            "attachments": [{
                "color": self._get_slack_color(),
                "title": f"{severity_emoji.get(self.severity, '')} {self.title}",
                "fields": [
                    {"title": "服务器", "value": self.server_name, "short": True},
                    {"title": "指标", "value": self.metric_name, "short": True},
                    {"title": "当前值", "value": str(self.current_value), "short": True},
                    {"title": "阈值", "value": str(self.threshold), "short": True},
                ],
                "text": self.content,
                "footer": "AiOps",
                "ts": int(time.time())
            }]
        }
    
    def _get_slack_color(self):
        return {'P0': 'danger', 'P1': 'warning', 'P2': 'warning', 'P3': 'good'}.get(self.severity, '#439FE5')


class BaseChannel:
    """通知渠道基类"""
    
    channel_name = "base"
    
    def __init__(self, config: dict):
        self.config = config
    
    def send(self, message: NotificationMessage) -> Dict:
        """发送消息，返回结果字典"""
        raise NotImplementedError
    
    def validate_config(self) -> Tuple[bool, str]:
        """验证配置是否有效"""
        return True, ""


class DingTalkChannel(BaseChannel):
    """钉钉机器人 Webhook 渠道"""
    
    channel_name = "dingtalk"
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.webhook_url = config.get('webhook_url', '')
        self.secret = config.get('secret', '')
        self.msg_type = config.get('msg_type', 'text')  # text / markdown / action_card
    
    def send(self, message: NotificationMessage) -> Dict:
        import requests
        
        try:
            if self.msg_type == 'markdown':
                payload = message.to_dingtalk_markdown()
            else:
                payload = {
                    "msgtype": "text",
                    "text": {"content": message.to_dingtalk_text()}
                }
            
            # 签名 (如果配置了secret)
            if self.secret:
                timestamp = str(round(time.time() * 1000))
                string_to_sign = f'{timestamp}\n{self.secret}'
                hmac_code = hmac.new(
                    self.secret.encode(), string_to_sign.encode(), digestmod=hashlib.sha256
                ).digest()
                sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
                url = f"{self.webhook_url}&timestamp={timestamp}&sign={sign}"
            else:
                url = self.webhook_url
            
            resp = requests.post(url, json=payload, timeout=10)
            
            if resp.status_code == 200 and resp.json().get('errcode') == 0:
                return {'success': True, 'channel': self.channel_name, 'response': resp.json()}
            else:
                return {'success': False, 'channel': self.channel_name, 
                        'error': resp.json().get('errmsg', 'unknown')}
                        
        except Exception as e:
            logger.error(f"[DingTalk] Send failed: {e}")
            return {'success': False, 'channel': self.channel_name, 'error': str(e)}
    
    def validate_config(self) -> Tuple[bool, str]:
        if not self.webhook_url:
            return False, "缺少 webhook_url 配置"
        if not self.webhook_url.startswith('https://oapi.dingtalk.com'):
            return False, "Webhook URL 格式不正确"
        return True, ""


class WeChatWorkChannel(BaseChannel):
    """企业微信机器人 Webhook 渠道"""
    
    channel_name = "wechat"
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.webhook_url = config.get('webhook_url', '')
    
    def send(self, message: NotificationMessage) -> Dict:
        import requests
        
        try:
            payload = {
                "msgtype": "markdown",
                "markdown": {
                    "content": message.to_wechat_text()
                }
            }
            
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            
            if resp.status_code == 200 and resp.json().get('errcode') == 0:
                return {'success': True, 'channel': self.channel_name}
            else:
                return {'success': False, 'channel': self.channel_name,
                        'error': resp.json().get('errmsg', 'unknown')}
                
        except Exception as e:
            logger.error(f"[WeChatWork] Send failed: {e}")
            return {'success': False, 'channel': self.channel_name, 'error': str(e)}


class EmailChannel(BaseChannel):
    """邮件通知渠道"""
    
    channel_name = "email"
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.smtp_host = config.get('smtp_host', 'smtp.example.com')
        self.smtp_port = config.get('smtp_port', 587)
        self.smtp_user = config.get('smtp_user', '')
        self.smtp_pass = config.get('smtp_pass', '')
        self.from_addr = config.get('from_addr', '')
        self.use_tls = config.get('use_tls', True)
    
    def send(self, message: NotificationMessage) -> Dict:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{message.severity}] {message.title}"
            msg['From'] = self.from_addr
            msg['To'] = self.config.get('to_addrs', '')
            
            html_content = message.to_email_html()
            msg.attach(MIMEText(html_content, 'html', 'utf-8'))
            
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            if self.use_tls:
                server.starttls()
            server.login(self.smtp_user, self.smtp_pass)
            server.sendmail(self.from_addr, self.config.get('to_addrs', '').split(','), msg.as_string())
            server.quit()
            
            return {'success': True, 'channel': self.channel_name}
            
        except Exception as e:
            logger.error(f"[Email] Send failed: {e}")
            return {'success': False, 'channel': self.channel_name, 'error': str(e)}


class SlackChannel(BaseChannel):
    """Slack Incoming Webhook 渠道"""
    
    channel_name = "slack"
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.webhook_url = config.get('webhook_url', '')
    
    def send(self, message: NotificationMessage) -> Dict:
        import requests
        
        try:
            payload = message.to_slack_attachment()
            resp = requests.post(self.webhook_url, json=payload, timeout=10)
            
            if resp.status_code == 200 and resp.json().get('ok'):
                return {'success': True, 'channel': self.channel_name}
            else:
                return {'success': False, 'channel': self.channel_name,
                        'error': resp.text}
                
        except Exception as e:
            return {'success': False, 'channel': self.channel_name, 'error': str(e)}


class WebhookChannel(BaseChannel):
    """通用 Webhook 回调渠道 (可对接任何系统)"""
    
    channel_name = "webhook"
    
    def __init__(self, config: dict):
        super().__init__(config)
        self.url = config.get('url', '')
        self.method = config.get('method', 'POST')
        self.headers = config.get('headers', {})
        self.template = config.get('template', None)  # 自定义JSON模板
    
    def send(self, message: NotificationMessage) -> Dict:
        import requests
        
        try:
            if self.template:
                # 使用自定义模板渲染
                payload = self._render_template(message)
            else:
                payload = {
                    "alert_id": message.alert_id,
                    "title": message.title,
                    "content": message.content,
                    "severity": message.severity,
                    "server": message.server_name,
                    "metric": message.metric_name,
                    "current_value": message.current_value,
                    "threshold": message.threshold,
                    "timestamp": message.timestamp,
                }
            
            resp = requests.request(
                self.method, self.url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            return {
                'success': resp.status_code < 400,
                'channel': self.channel_name,
                'status_code': resp.status_code
            }
            
        except Exception as e:
            return {'success': False, 'channel': self.channel_name, 'error': str(e)}
    
    def _render_template(self, message):
        """渲染自定义模板 (简单变量替换)"""
        template_str = json.dumps(self.template)
        replacements = {
            '{{title}}': message.title,
            '{{content}}': message.content,
            '{{severity}}': message.severity,
            '{{server}}': message.server_name,
            '{{metric}}': message.metric_name,
            '{{value}}': str(message.current_value),
            '{{threshold}}': str(message.threshold),
        }
        for k, v in replacements.items():
            template_str = template_str.replace(k, v)
        return json.loads(template_str)


class NotificationRouter:
    """通知路由器 - 负责选择渠道和分发"""
    
    CHANNEL_MAP = {
        'dingtalk': DingTalkChannel,
        'wechat': WeChatWorkChannel,
        'email': EmailChannel,
        'slack': SlackChannel,
        'webhook': WebhookChannel,
    }
    
    def __init__(self):
        self.channels = {}
        self._load_channels_from_db()
    
    def _load_channels_from_db(self):
        """从数据库加载已配置的渠道"""
        from system.models import SystemConfig
        
        for name, cls in self.CHANNEL_MAP.items():
            config_raw = SystemConfig.objects.filter(key=f'notify_{name}_config').first()
            if config_raw and config_raw.value:
                try:
                    config = json.loads(config_raw.value)
                    valid, err = cls(config).validate_config()
                    if valid:
                        self.channels[name] = cls(config)
                    else:
                        logger.warning(f"[Notify] Channel {name} config invalid: {err}")
                except Exception as e:
                    logger.error(f"[Notify] Failed to load channel {name}: {e}")
    
    def route_and_send(self, message: NotificationMessage, target_channels: List[str]) -> List[Dict]:
        """
        路由并分发通知
        
        Args:
            message: 通知消息
            target_channels: 目标渠道列表 ['dingtalk', 'wechat', ...]
        
        Returns:
            各渠道发送结果列表
        """
        results = []
        
        for channel_name in target_channels:
            channel = self.channels.get(channel_name)
            if not channel:
                results.append({
                    'success': False, 'channel': channel_name,
                    'error': 'channel_not_configured'
                })
                continue
            
            result = channel.send(message)
            results.append(result)
            
            status = "✅" if result['success'] else "❌"
            logger.info(f"[Notify] {status} {channel_name}: {result.get('error', 'OK')}")
        
        return results


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_alert_notifications(self, alert_event_id):
    """
    Celery 异步任务: 发送告警通知
    支持重试机制和失败记录
    """
    from monitoring.models import AlertEvent, AlertRule
    
    try:
        event = AlertEvent.objects.select_related('rule', 'server').get(id=alert_event_id)
        
        # 构建消息
        message = NotificationMessage(
            title=f"【{event.rule.name}】{event.message}",
            content=event.detail or "",
            severity=event.severity,
            alert_id=event.id,
            server_name=event.server.hostname if event.server else "未知",
            metric_name=event.metric_name,
            current_value=event.current_value,
            threshold=event.threshold_value or 0,
        )
        
        # 获取目标渠道
        channels = event.rule.notify_channels or ['dingtalk']
        
        # 发送通知
        router = NotificationRouter()
        results = router.route_and_send(message, channels)
        
        # 记录通知日志
        event.notification_log = results
        event.save(update_fields=['notification_log'])
        
        # 如果全部失败，重试
        all_failed = all(not r['success'] for r in results)
        if all_failed and self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        
        return results
        
    except AlertEvent.DoesNotExist:
        return {'error': 'alert_event_not_found'}
    except Exception as e:
        logger.error(f"[Alert Notify] Error for event {alert_event_id}: {e}")
        raise self.retry(exc=e)
```

---

## 10. 核心模块五：监控数据可视化平台

### 10.1 前端架构设计

```javascript
// monitoring/frontend/src/components/MonitorDashboard.vue

/**
 * AiOps 实时监控仪表盘
 * 技术栈: Vue3 + ECharts5 + WebSocket
 */

<template>
  <div class="monitor-dashboard">
    <!-- 顶部概览卡片 -->
    <a-row :gutter="16" class="overview-cards">
      <a-col :span="6" v-for="(card, idx) in overviewCards" :key="idx">
        <a-card class="metric-card" :class="'level-' + card.level">
          <div class="card-header">
            <span class="card-title">{{ card.title }}</span>
            <span class="card-value">{{ card.value }}{{ card.unit }}</span>
          </div>
          <div class="card-trend">
            <span :class="card.trend > 0 ? 'trend-up' : 'trend-down'">
              {{ card.trend > 0 ? '↑' : '↓' }} {{ Math.abs(card.trend) }}%
            </span>
            <span class="card-subtitle">较上周期</span>
          </div>
          <div class="mini-sparkline" :ref="'spark_' + idx"></div>
        </a-card>
      </a-col>
    </a-row>

    <!-- 主图表区域 -->
    <a-row :gutter="16" style="margin-top: 16px;">
      <!-- 趋势图 -->
      <a-col :span="16">
        <a-card title="实时趋势" size="small">
          <template #extra>
            <a-space>
              <a-select v-model="selectedMetric" style="width:120px;" @change="refreshChart">
                <a-option value="cpu_usage">CPU使用率</a-option>
                <a-option value="mem_usage">内存使用率</a-option>
                <a-option value="disk_usage">磁盘使用率</a-option>
                <a-option value="net_in">入站流量</a-option>
                <a-option value="net_out">出站流量</a-option>
              </a-select>
              <a-range-picker v-model="timeRange" @change="refreshChart" />
              <a-button type="link" @click="toggleFullscreen">全屏</a-button>
            </a-space>
          </template>
          <div ref="mainChart" style="height:400px;"></div>
        </a-card>
      </a-col>

      <!-- 告警面板 -->
      <a-col :span="8">
        <a-card title="活跃告警" size="small">
          <template #extra>
            <a-badge :count="activeAlertCount" :overflow-count="99">
              <a-button size="small">告警中心</a-button>
            </a-badge>
          </template>
          
          <div class="alert-list" v-if="activeAlerts.length">
            <div 
              v-for="alert in activeAlerts" 
              :key="alert.id"
              class="alert-item"
              :class="'severity-' + alert.severity"
            >
              <div class="alert-header">
                <a-tag :color="severityColor(alert.severity)">{{ alert.severity }}</a-tag>
                <span class="alert-server">{{ alert.server_name }}</span>
                <span class="alert-time">{{ formatTime(alert.fired_at) }}</span>
              </div>
              <div class="alert-message">{{ alert.message }}</div>
              <div class="alert-actions">
                <a-button size="small" type="primary" ghost @click="acknowledge(alert.id)">确认</a-button>
                <a-button size="small" danger ghost @click="silence(alert.id)">静默</a-button>
                <a-button size="small" @click="diagnose(alert)">AI诊断</a-button>
              </div>
            </div>
          </div>
          <a-empty v-else description="暂无活跃告警 🎉" />
        </a-card>

        <!-- 告警统计 -->
        <a-card title="24h告警分布" size="small" style="margin-top:16px;">
          <div ref="alertPieChart" style="height:200px;"></div>
        </a-card>
      </a-col>
    </a-row>

    <!-- 底部: Top N 排行榜 -->
    <a-row :gutter="16" style="margin-top: 16px;">
      <a-col :span="8">
        <a-card title="CPU Top 10" size="small">
          <div ref="cpuRankChart" style="height:250px;"></div>
        </a-card>
      </a-col>
      <a-col :span="8">
        <a-card title="内存 Top 10" size="small">
          <div ref="memRankChart" style="height:250px;"></div>
        </a-card>
      </a-col>
      <a-col :span="8">
        <a-card title="磁盘 Top 10" size="small">
          <div ref="diskRankChart" style="height:250px;"></div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'

// WebSocket 实时连接
let ws = null
const wsUrl = `ws://${window.location.host}/ws/monitor/`

// 响应式数据
const selectedMetric = ref('cpu_usage')
const timeRange = ref(null)
const activeAlerts = ref([])
const activeAlertCount = ref(0)
const overviewCards = ref([])

// ECharts 实例引用
const mainChart = ref(null)
const alertPieChart = ref(null)
const cpuRankChart = ref(null)
const memRankChart = ref(null)
const diskRankChart = ref(null)

let mainChartInstance = null

// 初始化主图表
function initMainChart() {
  if (!mainChart.value) return
  mainChartInstance = echarts.init(mainChart.value)
  
  const option = {
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['当前值', '阈值线', '基线'] },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', boundaryGap: false, data: [] },
    yAxis: { type: 'value', name: '%' },
    series: [
      { name: '当前值', type: 'line', smooth: true, data: [], areaStyle: {} },
      { name: '阈值线', type: 'line', lineStyle: { type: 'dashed', color: '#ff4d4f' }, data: [] },
      { name: '基线', type: 'line', lineStyle: { type: 'dotted', color: '#faad14' }, data: [] }
    ],
    // 标记告警点
    markPoint: {
      data: [], // 动态填充告警点
      symbol: 'pin',
      symbolSize: 40,
      itemStyle: { color: '#ff4d4f' }
    }
  }
  
  mainChartInstance.setOption(option)
}

// WebSocket 数据接收处理
function connectWebSocket() {
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => console.log('[WS] Monitor connected')
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    
    switch(data.type) {
      case 'metrics_update':
        updateChartData(data.payload)
        break
      case 'alert_fired':
        addAlertItem(data.payload)
        break
      case 'alert_resolved':
        resolveAlertItem(data.payload)
        break
      case 'overview_update':
        updateOverviewCards(data.payload)
        break
    }
  }
  
  ws.onclose = () => {
    console.log('[WS] Monitor disconnected, reconnecting...')
    setTimeout(connectWebSocket, 3000)  // 自动重连
  }
}

// 更新图表数据
function updateChartData(payload) {
  if (!mainChartInstance) return
  
  const option = mainChartInstance.getOption()
  
  // 追加新数据点
  option.xAxis[0].data.push(payload.time)
  option.series[0].data.push(payload.value)
  
  // 保持最近60个数据点
  const maxPoints = 60
  if (option.xAxis[0].data.length > maxPoints) {
    option.xAxis[0].data.shift()
    option.series[0].data.shift()
  }
  
  mainChartInstance.setOption(option)
}

// 告警项操作
async function acknowledge(alertId) {
  await fetch(`/api/alerts/${alertId}/acknowledge/`, { method: 'POST' })
  activeAlerts.value = activeAlerts.value.filter(a => a.id !== alertId)
}

async function silence(alertId) {
  await fetch(`/api/alerts/${alertId}/silence/`, { method: 'POST' })
}

function diagnose(alert) {
  // 触发 AI 诊断弹窗
  window.dispatchEvent(new CustomEvent('ai-diagnose', { detail: alert }))
}

// 工具函数
function severityColor(sev) {
  return { P0: 'red', P1: 'orange', P2: 'gold', P3: 'blue' }[sev] || 'default'
}
function formatTime(isoStr) {
  return new Date(isoStr).toLocaleString('zh-CN')
}

onMounted(() => {
  nextTick(() => {
    initMainChart()
    connectWebSocket()
  })
})

onUnmounted(() => {
  if (ws) ws.close()
  if (mainChartInstance) mainChartInstance.dispose()
})
</script>

<style scoped>
.metric-card { border-radius: 8px; transition: all 0.3s; }
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
.level-P0 { border-left: 4px solid #ff4d4f; }
.level-P1 { border-left: 4px solid #fa8c16; }
.level-P2 { border-left: 4px solid #faad14; }
.level-P3 { border-left: 4px solid #52c41a; }

.alert-item { padding: 12px; border-bottom: 1px solid #f0f0f0; }
.alert-item:last-child { border-bottom: none; }
.severity-P0 { background: #fff2f0; border-left: 3px solid #ff4d4f; }
.severity-P1 { background: #fff7e6; border-left: 3px solid #fa8c16; }
.severity-P2 { background: #fffbe6; border-left: 3px solid #faad14; }
.severity-P3 { background: #f6ffed; border-left: 3px solid #52c41a; }
</style>
```

---

## 11. 数据库模型设计补充说明

### 11.1 监控相关模型迁移策略

```python
# monitoring/migrations/0001_initial.py

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('cmdb', '0001_initial'),
        ('system', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlertRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, unique=True, verbose_name='规则名称')),
                ('description', models.TextField(blank=True, verbose_name='规则描述')),
                ('rule_type', models.CharField(choices=[
                    ('threshold', '静态阈值'), ('baseline', '动态基线'), ('trend', '趋势检测'),
                    ('composite', '复合条件'), ('absence', '消失检测'), ('anomaly', '异常检测')
                ], default='threshold', max_length=20, verbose_name='规则类型')),
                ('severity', models.CharField(choices=[
                    ('P0', '致命'), ('P1', '严重'), ('P2', '警告'), ('P3', '提示')
                ], default='P1', max_length=10, verbose_name='严重级别')),
                ('status', models.CharField(choices=[
                    ('enabled', '启用'), ('disabled', '禁用'), ('draft', '草稿')
                ], default='enabled', max_length=20, verbose_name='状态')),
                ('target_all', models.BooleanField(default=True, verbose_name='应用于所有服务器')),
                ('metric_name', models.CharField(help_text='cpu_usage/mem_usage/disk_usage/load_1min/net_in/net_out', max_length=50, verbose_name='监控指标')),
                ('condition_config', models.JSONField(default=dict, verbose_name='条件配置')),
                ('evaluate_interval', models.PositiveIntegerField(default=60, help_text='多久评估一次该规则', verbose_name='评估间隔(秒)')),
                ('lookback_window', models.PositiveIntegerField(default=5, help_text='取最近N个数据点进行判断', verbose_name='回溯窗口(个)')),
                ('cooldown_seconds', models.PositiveIntegerField(default=300, help_text='同一目标触发后N秒内不再重复触发', verbose_name='冷却时间(秒)')),
                ('max_alerts_per_hour', models.PositiveIntegerField(default=10, help_text='防告警风暴限制', verbose_name='每小时最大告警数')),
                ('notify_channels', models.JSONField(default=list, verbose_name='通知渠道')),
                ('notify_template', models.TextField(blank=True, default='', verbose_name='通知模板')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_triggered_at', models.DateTimeField(blank=True, null=True, verbose_name='最后触发时间')),
                ('trigger_count', models.PositiveIntegerField(default=0, verbose_name='累计触发次数')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='system.user')),
            ],
            options={
                'verbose_name': '预警规则',
                'verbose_name_plural': '预警规则',
                'ordering': ['-created_at'],
                'indexes': [
                    models.Index(fields=['status', 'rule_type'], name='idx_alert_rule_status_type'),
                    models.Index(fields=['severity'], name='idx_alert_rule_severity'),
                ],
            },
        ),
        
        migrations.CreateModel(
            name='AlertEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[
                    ('firing', '触发中'), ('resolved', '已恢复'), ('acknowledged', '已确认'), ('silenced', '已静默')
                ], default='firing', max_length=20, verbose_name='状态')),
                ('severity', models.CharField(max_length=10, verbose_name='级别')),
                ('metric_name', models.CharField(max_length=50, verbose_name='指标名')),
                ('current_value', models.FloatField(verbose_name='当前值')),
                ('threshold_value', models.FloatField(blank=True, null=True, verbose_name='阈值/基线')),
                ('message', models.TextField(default='', verbose_name='告警消息')),
                ('detail', models.JSONField(default=dict, verbose_name='详细信息')),
                ('fired_at', models.DateTimeField(auto_now_add=True, verbose_name='触发时间')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='恢复时间')),
                ('acknowledged_at', models.DateTimeField(blank=True, null=True, verbose_name='确认时间')),
                ('notification_log', models.JSONField(default=list, verbose_name='通知记录')),
                ('rule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='monitoringalertrule')),
                ('server', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='alert_events', to='cmdbserver')),
                ('acknowledged_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='system.user')),
            ],
            options={
                'verbose_name': '告警事件',
                'verbose_name_plural': '告警事件',
                'ordering': ['-fired_at'],
                'indexes': [
                    models.Index(fields=['status', '-fired_at'], name='idx_alert_event_status_time'),
                    models.Index(fields=['server', 'status'], name='idx_alert_event_server_status'),
                ],
            },
        ),
        
        migrations.CreateModel(
            name='AlertSilenceRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='静默名称')),
                ('match_severity', models.CharField(blank=True, default='', max_length=10, verbose_name='匹配级别')),
                ('match_rule_name', models.CharField(blank=True, default='', max_length=200, verbose_name='匹配规则')),
                ('start_time', models.DateTimeField(verbose_name='开始时间')),
                ('end_time', models.DateTimeField(verbose_name='结束时间')),
                ('comment', models.TextField(blank=True, verbose_name='备注')),
                ('is_active', models.BooleanField(default=True, verbose_name='生效中')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='system.user')),
                ('match_server', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='cmdbserver')),
            ],
        ),
        
        migrations.CreateModel(
            name='AlertEscalationPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='策略名称')),
                ('levels', models.JSONField(default=list, verbose_name='升级层级')),
                ('is_active', models.BooleanField(default=True)),
                ('rule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='escalations', to='monitoringalertrule')),
            ],
        ),
        
        # Many-to-Many 关系字段
        migrations.AddField(
            model_name='alertrule',
            name='target_servers',
            field=models.ManyToManyField(blank=True, related_name='alert_rules', to='cmdb.server', verbose_name='目标服务器'),
        ),
        migrations.AddField(
            model_name='alertrule',
            name='target_groups',
            field=models.ManyToManyField(blank=True, related_name='alert_rules', to='cmdb.servergroup', verbose_name='目标分组'),
        ),
        migrations.AddField(
            model_name='alertrule',
            name='notify_users',
            field=models.ManyToManyField(blank=True, to='system.user', verbose_name='通知人员'),
        ),
    ]
```

---

## 12. API 接口规范

### 12.1 RESTful API 设计

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| **规则管理** ||||
| GET | `/api/v1/rules/` | 规则列表 (分页+筛选) | login |
| POST | `/api/v1/rules/` | 创建规则 | admin |
| GET | `/api/v1/rules/{id}/` | 规则详情 | login |
| PUT | `/api/v1/rules/{id}/` | 更新规则 | admin |
| DELETE | `/api/v1/rules/{id}/` | 删除规则 | admin |
| POST | `/api/v1/rules/{id}/toggle/` | 启用/禁用规则 | admin |
| POST | `/api/v1/rules/{id}/test/` | 测试规则(Dry Run) | admin |
| **告警事件** ||||
| GET | `/api/v1/alerts/` | 告警列表 (分页+筛选) | login |
| GET | `/api/v1/alerts/stats/` | 告警统计摘要 | login |
| GET | `/api/v1/alerts/{id}/` | 告警详情 | login |
| POST | `/api/v1/alerts/{id}/acknowledge/` | 确认告警 | login |
| POST | `/api/v1/alerts/{id}/resolve/` | 手动解决 | login |
| POST | `/api/v1/alerts/{id}/silence/` | 静默告警 | admin |
| **静默管理** ||||
| GET | `/api/v1/silences/` | 静默规则列表 | login |
| POST | `/api/v1/silences/` | 创建静默规则 | admin |
| DELETE | `/api/v1/silences/{id}/` | 删除静默规则 | admin |
| **监控数据** ||||
| GET | `/api/v1/metrics/servers/{id}/latest/` | 最新指标 | login |
| GET | `/api/v1/metrics/servers/{id}/range/` | 时间范围查询 | login |
| GET | `/api/v1/metrics/overview/` | 全局概览数据 | login |
| **通知配置** ||||
| GET | `/api/v1/notification/channels/` | 已配置渠道列表 | admin |
| PUT | `/api/v1/notification/channels/{name}/` | 更新渠道配置 | admin |
| POST | `/api/v1/notification/test/` | 发送测试消息 | admin |

### 12.2 API 响应格式规范

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [...],
    "total": 100,
    "page": 1,
    "page_size": 20
  },
  "request_id": "uuid-xxx",
  "timestamp": "2026-04-13T10:30:00Z"
}
```

---

## 13. 高可用与扩展性设计

### 13.1 高可用架构要点

```
┌─────────────────────────────────────────────────────────────┐
│                    HA 架构设计                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  采集层 HA:                                                  │
│  ├── 多实例采集器 (Celery Worker × N)                        │
│  ├── Redis 分布式锁防重复采集                                 │
│  └── 采集任务失败自动重新分配                                 │
│                                                              │
│  存储层 HA:                                                  │
│  ├── PostgreSQL 主从复制 (读写分离)                           │
│  ├── Prometheus Federation / Remote Write                   │
│  └── Redis Sentinel / Cluster                                │
│                                                              │
│  应用层 HA:                                                  │
│  ├── Django Gunicorn × N (多进程)                            │
│  ├── Nginx 负载均衡 + upstream                               │
│  └── Celery Beat 单点 → 替换为 RedBeat (Redis-based)         │
│                                                              │
│  告警层 HA:                                                  │
│  └── 告警事件队列 (Redis List) + 消费者组                     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 13.2 扩展性设计原则

| 原则 | 实现方式 |
|------|---------|
| **水平扩展** | 无状态Worker，通过Redis协调 |
| **插件化** | 渠道/检测器采用注册机制，可动态加载 |
| **配置驱动** | 所有阈值/渠道/路由均DB可配，无需改代码 |
| **版本兼容** | 规则支持版本控制，变更可回滚 |
| **多租户** | RBAC分组隔离，数据按权限过滤 |

---

## 15. 分阶段实施路线图

### Phase 1: 基础告警能力 (预计 2-3 周)

```
Week 1:
├── [ ] 创建 monitoring 应用和数据库模型
├── [ ] 实现 AlertRule CRUD (Django Admin + API)
├── [ ] 实现基础 Threshold 规则评估引擎
├── [ ] 改造现有 send_alert 为 NotificationRouter
└── [ ] 告警事件记录与列表页

Week 2-3:
├── [ ] AlertEvent 确认/解决/静默操作
├── [ ] Dashboard 告警面板嵌入
├── [ ] 冷却期与频率限制实现
├── [ ] 钉钉Markdown卡片优化
└── [ ] 单元测试覆盖核心逻辑
```

### Phase 2: 异常检测集成 (预计 2 周)

```
Week 4:
├── [ ] ZScoreDetector + IQRDetector 实现
├── [ ] MovingAverageDetector + RateOfChangeDetector
├── [ ] CompositeAnomalyDetector 组合投票
├── [ ] 与 RuleEngine 的 anomaly 类型对接
└── [ ] 异常检测结果可视化标注

Week 5:
├── [ ] AI诊断自动联动 (异常→触发LLM分析)
├── [ ] 检测算法参数调优界面
├── [ ] 历史异常回溯分析功能
└── [ ] 性能测试 (100台服务器场景)
```

### Phase 3: 可视化升级 (预计 2 周)

```
Week 6:
├── [ ] Vue3 MonitorDashboard 组件开发
├── [ ] ECharts 实时趋势图 (WebSocket推送)
├── [ ] 告警面板实时更新
├── [ ] Top N 排行榜组件
└── [ ] 时间范围选择器

Week 7:
├── [ ] Grafana 数据源对接 (可选)
├── [ ] 自定义Widget拖拽布局
├── [ ] 告警叠加标记到趋势图
├── [ ] PDF报告导出
└── [ ] 移动端适配
```

### Phase 4: 企业级增强 (持续迭代)

```
Month 2+:
├── [ ] Prometheus 时序存储集成
├── [ ] 邮件/短信/Slack等多渠道完善
├── [ ] 值班表 (On-Call) 与升级链路
├── [ ] 告警聚合与降噪算法
├── [ ] Grafana Embedded Dashboard
├── [ ] SLO/SLI 可用性追踪
└── [ ] ChatOps 集成 (告警在IM中直接处理)
```

---

## 16. 附录：关键文件索引与代码位置参考

### A. 现有监控相关文件清单

| 文件路径 | 功能描述 | 当前状态 |
|---------|---------|---------|
| [cmdb/models.py](file:///d:/codes/aiops/cmdb/models.py) | ServerMetric/SSLCertificate 模型定义 | ✅ 已实现 |
| [cmdb/tasks.py](file:///d:/codes/aiops/cmdb/tasks.py) | SSL证书检测+钉钉/企微通知 | ⚠️ 仅SSL告警 |
| [cmdb/views.py](file:///d:/codes/aiops/cmdb/views.py) | SSL证书管理视图 | ✅ 已实现 |
| [cmdb/agent_code.py](file:///d:/codes/aiops/cmdb/agent_code.py) | Agent部署脚本 (psutil采集) | ✅ 已实现 |
| [cmdb/consumers.py](file:///d:/codes/aiops/cmdb/consumers.py) | WebSSH WebSocket + 高危命令拦截 | ✅ 已实现 |
| [cmdb/management/commands/run_agent.py](file:///d:/codes/aiops/cmdb/management/commands/run_agent.py) | 服务器指标采集 (Agent+SSH双模式) | ✅ 已实现 |
| [k8s_manager/management/commands/collect_k8s.py](file:///d:/codes/aiops/k8s_manager/management/commands/collect_k8s.py) | K8s集群节点指标采集 | ✅ 已实现 |
| [system/views.py](file:///d:/codes/aiops/system/views.py) | Dashboard视图 (趋势图表) | ⚠️ 基础版 |
| [ai_ops/views.py](file:///d://codes/aiops/ai_ops/views.py) | AI故障诊断/审计/风险评估 | ✅ 有亮点 |
| [system/models.py](file:///d:/codes/aiops/system/models.py) | SystemConfig (KV配置) | ✅ 已实现 |

### B. 新增文件规划清单 (待创建)

| 文件路径 | 功能描述 | Phase |
|---------|---------|-------|
| `monitoring/__init__.py` | 应用初始化 | P1 |
| `monitoring/apps.py` | Django App 配置 | P1 |
| `monitoring/models.py` | AlertRule/AlertEvent/Silence/Escalation | P1 |
| `monitoring/engine/rule_evaluator.py` | 规则引擎核心 | P1 |
| `monitoring/engine/__init__.py` | 引擎包初始化 | P1 |
| `monitoring/anomaly_detector.py` | 异常检测算法库 | P2 |
| `monitoring/notification/channel_manager.py` | 多渠道通知中心 | P1 |
| `monitoring/notification/__init__.py` | 通知包初始化 | P1 |
| `monitoring/collectors/enhanced_collector.py` | 增强版采集器 | P2 |
| `monitoring/collectors/__init__.py` | 采集包初始化 | P2 |
| `monitoring/api/views.py` | REST API 视图 | P1 |
| `monitoring/api/urls.py` | API 路由 | P1 |
| `monitoring/admin.py` | Django Admin 注册 | P1 |
| `monitoring/websocket/consumers.py` | WebSocket 实时推送 | P3 |
| `monitoring/templates/dashboard.html` | 监控仪表盘模板 | P3 |
| `monitoring/management/commands/rule_evaluator.py` | 规则评估定时任务 | P1 |
| `monitoring/migrations/0001_initial.py` | 数据库迁移 | P1 |

### C. 第三方依赖新增

```txt
# requirements.txt 新增依赖

# 异常检测
scikit-learn>=1.3.0
statsmodels>=0.14.0
numpy>=1.24.0

# Prometheus 集成 (可选)
prometheus-client>=0.19.0
prometheus-api-client>=0.5.0

# Grafana 集成 (可选)
grafana-api>=1.0.3

# 可视化前端 (如需独立服务)
# 已有ECharts, 无需额外安装
```

---

> **文档结束** — 本文档共涵盖 16 个章节，包含完整的现状分析、架构设计、核心代码示例、实施路线图及附录。所有代码均已针对 AiOps 项目现有技术栈 (Django 5.x + Celery + Redis + Vue3) 进行定制化设计，可直接作为开发参考。
    
    def _z_score(self, value, mean, std):
        """计算 Z-Score"""
        if std == 0:
            return 0
        return abs((value - mean) / std)


class StaticThresholdDetector(BaseDetector):
    """静态阈值检测器 (最简单但最常用)"""
    
    method_name = "static_threshold"
    
    def __init__(self, upper=None, lower=None):
        self.upper = upper
        self.lower = lower or 0
    
    def detect(self, series: List[float]) -> AnomalyResult:
        if not series:
            return AnomalyResult(False, 0, self.method_name, "empty_series")
        
        latest = series[-1]
        
        is_high = self.upper and latest > self.upper
        is_low = latest < self.lower
        
        if is_high:
            score = min(1.0, (latest - self.upper) / self.upper)
            return AnomalyResult(True, score, self.method_name, 
                f"值 {latest:.2f} 超过上限 {self.upper}", {'direction': 'high'})
        elif is_low:
            score = min(1.0, (self.lower - latest) / self.lower)
            return AnomalyResult(True, score, self.method_name,
                f"值 {latest:.2f} 低于下限 {self.lower}", {'direction': 'low'})
        
        return AnomalyResult(False, 0, self.method_name, "normal")


class ZScoreDetector(BaseDetector):
    """Z-Score 统计检测器 (适合正态分布数据)"""
    
    method_name = "zscore"
    
    def __init__(self, threshold=3.0, window=30):
        self.threshold = threshold
        self.window = window
    
    def detect(self, series: List