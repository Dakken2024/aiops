# AiOps 实时预警与监控 — Phase 3 可视化升级执行计划

**文档版本**: v1.0-EXEC  
**创建日期**: 2026-04-13  
**基于**: `realtime-alerting-monitoring-analysis-and-implementation.md` §15 分阶段实施路线图  
**前置条件**: Phase 1 + Phase 2 全部完成  
**目标**: 实现实时数据推送、可视化组件增强、TopN排行、时间范围选择、PDF报告导出

---

## 📋 Phase 3 范围定义

### 本阶段交付物

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | **WebSocket 实时推送通道** | Django Channels 实现 metrics/alerts 双向实时通信 |
| 2 | **指标数据广播任务** | Celery 定时采集 → WebSocket 广播最新指标 |
| 3 | **告警事件实时广播** | 新告警触发时立即推送到所有在线 Dashboard |
| 4 | **Top N 排行榜** | CPU/内存/磁盘/负载 Top10 排名 + 前端表格组件 |
| 5 | **时间范围选择器** | 支持 1h/6h/24h/7d/30d 聚合查询 API |
| 6 | **Dashboard 实时刷新改造** | 前端 JS 集成 WebSocket，自动更新图表和数值 |
| 7 | **PDF 报告导出** | 服务器监控报告一键生成下载 |

### 不在本阶段范围

- Vue3 前端重写 (独立项目)
- Grafana 数据源对接 (Phase 4)
- Prometheus 时序存储集成 (Phase 4)
- 移动端适配 (Phase 4)

---

## 🔧 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                     Phase 3 新增模块                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │ W6-1: WS Push     │    │ W6-3: Alert Broadcast        │   │
│  │                  │    │                              │   │
│  │ MetricsConsumer  │◄───┼── RuleEvaluator._fire()      │   │
│  │ ┌──────────────┐ │    │       ↓                      │   │
│  │ │ ws://.../ws/  │ │    │ channel_layer.group_send()  │   │
│  │ │ monitoring/   │ │    │       ↓                      │   │
│  │ └──────┬───────┘ │    │ 所有 Dashboard 收到告警通知    │   │
│  │         ▼         │    └──────────────────────────────┘   │
│  │  Browser JS      │                                      │
│  │  (ECharts update)│    ┌──────────────────────────────┐   │
│  └──────────────────┘    │ W6-2: Celery Broadcast Task   │   │
│                          │                              │   │
│  ┌──────────────────┐    │ broadcast_metrics.delay()    │   │
│  │ W6-4: TopN Rank  │    │       ↓                      │   │
│  │                  │    │ 查询 ServerMetric 最新值      │   │
│  │ GET /api/topn/   │    │ → channel_layer.group_send() │   │
│  │ cpu/mem/disk/    │    │       ↓                      │   │
│  │ load             │    │ 所有连接客户端收到指标更新     │   │
│  └──────────────────┘    └──────────────────────────────┘   │
│                                                             │
│  ┌──────────────────┐    ┌──────────────────────────────┐   │
│  │ W6-5: Time Range │    │ W6-7: PDF Export              │   │
│  │                  │    │                              │   │
│  │ /api/trend/?range│    │ GET /api/report/pdf/          │   │
│  │ =1h|6h|24h|7d|30d│    │ → WeasyPrint → FileResponse  │   │
│  │ + 聚合降采样     │    │                              │   │
│  └──────────────────┘    └──────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 数据流 — WebSocket 实时推送

```
[Server Side]                          [Client Side]
                                        
Celery Beat (每60s)                        
  │                                    
  ▼                                    
broadcast_metrics_task()                 
  │                                    
  ├─→ 查询所有 Running 服务器的最新指标   
  │   SELECT * FROM server_metric ...    
  │                                    
  ▼                                    
channel_layer.group_send(                
  'monitoring',                          
  {type:'metrics_update', data:[...]}    
)                                       
  │                                    
  ╰═════════╤═══════════════════════════╯
          │ (WebSocket)
          ▼
  onmessage → JSON.parse()
      │
      ├─→ 更新 ECharts 图表 (chart.setOption)
      ├─→ 更新数值卡片 (CPU: 45%)
      ├─→ 更新仪表盘 (Load Gauge)
      └─→ 更新 TopN 排行表
```

---

## 📁 文件变更清单 (共需新建/修改 9 个文件)

```
新建文件 (5个):
├── monitoring/
│   ├── websocket/
│   │   ├── __init__.py
│   │   ├── consumers.py              ← W6-1/W6-3: WS Consumer (metrics+alerts)
│   │   └── routing.py                ← WS URL Routing
│   ├── management/commands/
│   │   └── broadcast_metrics.py      ← W6-2: Celery 定时广播任务
│   └── tasks.py                       ← 辅助任务函数

修改文件 (4个):
├── monitoring/api/views.py            ← W6-4/W6-5/W6-7: TopN/聚合/PDF API
├── monitoring/api/urls.py             ← 新增路由
├── templates/index.html               ← W6-6: 前端WS集成+TopN面板+时间选择器
└── ops_platform/settings.py           ← Channels 配置
```

---

## 🚀 详细执行步骤

---

## Step 1: WebSocket 实时推送基础设施

### 1.1 安装依赖

```bash
pip install channels channels-redis
```

### 1.2 settings.py 新增 Channels 配置

在 [ops_platform/settings.py](file:///d:/codes/aiops/ops_platform/settings.py) 中添加:

```python
INSTALLED_APPS += [
    'channels',
]

ASGI_APPLICATION = 'ops_platform.asgi.application'

CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            "hosts": [(os.environ.get('REDIS_URL', 'redis://127.0.0.1'), 6379)],
        },
    },
}
```

### 1.3 创建 ASGI 入口文件

`ops_platform/asgi.py`:
```python
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
from monitoring.websocket.routing import websocket_urlpatterns

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AllowedHostsOriginValidator(
        URLRouter(websocket_urlpatterns)
    ),
})
```

### 1.4 创建 WebSocket Consumer

`monitoring/websocket/consumers.py`:
```python
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class MonitoringConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = 'monitoring'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        
        # 连接成功后发送欢迎消息 + 当前状态
        await self.send(text_data=json.dumps({
            'type': 'connected',
            'message': 'WebSocket connected',
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')
        
        if action == 'ping':
            await self.send(text_data=json.dumps({'type': 'pong'}))

    async def monitoring_event(self, event):
        """接收来自 Channel Layer 的广播消息"""
        await self.send(text_data=json.dumps(event['data']))
```

### 1.5 WebSocket Routing

`monitoring/websocket/routing.py`:
```python
from django.urls import re_path
from .consumers import MonitoringConsumer

websocket_urlpatterns = [
    re_path(r'ws/monitoring/$', MonitoringConsumer.as_asgi()),
]
```

---

## Step 2: 实时指标广播 Celery Task

`monitoring/management/commands/broadcast_metrics.py`:

```python
from celery import shared_task
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Avg, Max
from datetime import timedelta
from django.utils import timezone

@shared_task
def broadcast_metrics():
    """定时广播所有服务器最新指标到 WebSocket"""
    from cmdb.models import Server, ServerMetric
    
    channel_layer = get_channel_layer()
    
    servers = Server.objects.filter(status='Running')
    metrics_list = []
    
    for server in servers:
        try:
            latest = ServerMetric.objects.filter(server=server).latest('collected_at')
            metrics_list.append({
                'server_id': server.id,
                'hostname': server.hostname,
                'ip_address': server.ip_address,
                'cpu_usage': round(latest.cpu_usage, 2),
                'mem_usage': round(latest.mem_usage, 2),
                'disk_usage': round(latest.disk_usage, 2),
                'load_1min': round(getattr(latest, 'load_1min', 0), 2),
                'net_in': round(getattr(latest, 'net_in', 0), 2),
                'net_out': round(getattr(latest, 'net_out', 0), 2),
                'collected_at': latest.collected_at.isoformat(),
            })
        except Exception:
            continue
    
    if not metrics_list:
        return {'status': 'no_data'}
    
    cluster_avg = {
        'cpu': round(sum(m['cpu_usage'] for m in metrics_list) / len(metrics_list), 2),
        'mem': round(sum(m['mem_usage'] for m in metrics_list) / len(metrics_list), 2),
        'disk': round(sum(m['disk_usage'] for m in metrics_list) / len(metrics_list), 2),
    }
    
    async_to_sync(channel_layer.group_send)('monitoring', {
        'type': 'monitoring_event',
        'data': {
            'event_type': 'metrics_update',
            'timestamp': timezone.now().isoformat(),
            'servers': metrics_list,
            'cluster_avg': cluster_avg,
            'total_count': len(metrics_list),
        }
    })
    
    return {'status': 'ok', 'count': len(metrics_list)}
```

### Celery Beat 配置 (settings.py)

```python
CELERY_BEAT_SCHEDULE = {
    'broadcast-metrics-every-30s': {
        'task': 'monitoring.management.commands.broadcast_metrics.broadcast_metrics',
        'schedule': 30.0,  # 每30秒广播一次
    },
}
```

---

## Step 3: 告警实时广播机制

在 `rule_evaluator.py` 的 `_fire()` 方法末尾追加广播逻辑:

```python
# 在 _fire() 方法中，创建 AlertEvent 后追加:
try:
    from channels.layers import get_channel_layer
    from asgiref.sync import async_to_sync
    import json
    
    channel_layer = get_channel_layer()
    alert_payload = {
        'event_type': 'alert_fired',
        'alert_id': event.id,
        'rule_name': event.rule.name,
        'severity': event.severity,
        'server_hostname': server.hostname if server else '',
        'metric_name': event.metric_name,
        'current_value': event.current_value,
        'message': event.message,
        'fired_at': event.fired_at.isoformat(),
    }
    async_to_sync(channel_layer.group_send)('monitoring', {
        'type': 'monitoring_event',
        'data': alert_payload
    })
except Exception as e:
    logger.warning(f"[RuleEngine] 告警广播失败: {e}")
```

---

## Step 4: Top N 排行榜

### 4.1 API 端点

`api/views.py` 新增:

```python
@login_required
@require_GET
def api_topn(request):
    metric = request.GET.get('metric', 'cpu_usage')
    limit = int(request.GET.get('limit', 10))
    
    valid_metrics = ['cpu_usage', 'mem_usage', 'disk_usage', 'load_1min',
                     'net_in', 'net_out']
    if metric not in valid_metrics:
        return JsonResponse({'code':1,'msg':'无效指标'})
    
    field_map = {
        'cpu_usage': 'cpu_usage','mem_usage': 'mem_usage',
        'disk_usage': 'disk_usage','load_1min': 'load_1min',
        'net_in': 'net_in','net_out': 'net_out',
    }
    db_field = field_map.get(metric)
    
    from cmdb.models import Server, ServerMetric
    from django.db.models import Max
    
    subq = ServerMetric.objects.filter(
        server=models.OuterRef('id')
    ).order_by('-collected_at')[:1]
    
    qs = Server.objects.filter(status='Running').annotate(
        latest_val=Subquery(subq.values(db_field)[:1])
    ).exclude(latest_val__isnull=True).order_by('-latest_val')[:limit]
    
    items = [{
        'rank': i+1,
        'server_id': s.id,
        'hostname': s.hostname,
        'ip_address': s.ip_address,
        'value': round(s.latest_val or 0, 2),
    } for i, s in enumerate(qs)]
    
    return JsonResponse({'code':0,'data':{'metric':metric,'items':items}})
```

### 4.2 前端组件 (index.html)

在 Dashboard 中新增 TopN 面板，包含:
- CPU Top 10 表格 (带颜色条)
- 内存 Top 10 表格
- 自动每30秒刷新

---

## Step 5: 时间范围选择器 + 数据聚合 API

### 5.1 聚合 API

```python
@login_required
@require_GET
def api_trend_aggregated(request):
    server_id = request.GET.get('server_id')
    metric = request.GET.get('metric', 'cpu_usage')
    range_str = request.GET.get('range', '24h')
    
    range_map = {'1h':1,'6h':6,'24h':24,'7d':168,'30d':720}
    hours = range_map.get(range_str, 24)
    
    since = timezone.now() - timedelta(hours=hours)
    
    # 根据范围决定采样间隔
    if hours <= 6:
        interval_minutes = 1
    elif hours <= 24:
        interval_minutes = 5
    elif hours <= 168:
        interval_minutes = 30
    else:
        interval_minutes = 120
    
    # ... 聚合查询逻辑 ...
    
    return JsonResponse({'code':0,'data':{
        'times':[...],'values':[...],
        'avg':float(avg),'max':float(max_val),'min':float(min_val)
    }})
```

### 5.2 前端时间选择器

HTML 按钮组: `[1h] [6h] [24h] [7d] [30d]`
点击后重新请求对应范围的图表数据

---

## Step 6: Dashboard 实时刷新改造

### 6.1 WebSocket 客户端代码

在 `index.html` 的 `<script>` 中添加:

```javascript
let ws = null;
const WS_URL = location.protocol === 'https:' ? 'wss://' : 'ws://'
    + window.location.host + '/ws/monitoring/';

function connectWS() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = function() {
        console.log('[WS] Connected');
        document.getElementById('ws-status').className = 'badge badge-success';
        document.getElementById('ws-status').textContent = '实时';
    };
    
    ws.onmessage = function(evt) {
        const msg = JSON.parse(evt.data);
        handleWSMessage(msg);
    };
    
    ws.onclose = function() {
        console.log('[WS] Disconnected, reconnecting...');
        setTimeout(connectWS, 5000);  // 5秒后自动重连
    };
}

function handleWSMessage(msg) {
    switch(msg.event_type) {
        case 'metrics_update':
            updateMetricsCards(msg.cluster_avg);
            updateCharts(msg.servers);
            break;
        case 'alert_fired':
            showAlertToast(msg);
            refreshAlertTable();
            break;
    }
}

// 页面加载后连接
connectWS();
```

### 6.2 数值卡片实时更新

```javascript
function updateMetricsCards(avg) {
    if (!avg) return;
    animateValue('cpu-value', avg.cpu, '%');
    animateValue('mem-value', avg.mem, '%');
    animateValue('disk-value', avg.disk, '%');
}

function animateValue(elementId, newValue, suffix) {
    const el = document.getElementById(elementId);
    if (!el) return;
    el.textContent = newValue + suffix;
    el.style.transition = 'color 0.3s';
    el.style.color = '#1890ff';
    setTimeout(() => { el.style.color = ''; }, 300);
}
```

### 6.3 告警 Toast 提示

```javascript
function showAlertToast(alertData) {
    const sevColors = {'P0':'#ff4d4f','P1':'#faad14','P2':'#1890ff'};
    // 显示右上角 Toast 通知
    // 播放提示音 (可选)
}
```

---

## Step 7: PDF 报告导出

### 7.1 API 端点

```python
@login_required
@require_GET
def api_report_pdf(request):
    server_id = request.GET.get('server_id')
    days = int(request.GET.get('days', 7))
    
    # ... 收集数据 ...
    # ... 使用 WeasyPrint 或 xhtml2pdf 渲染 HTML→PDF ...
    
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="monitor-report-{now}.pdf"'
    return response
```

### 7.2 前端触发按钮

Dashboard 顶部新增「导出报告」按钮 → 触发下载

---

## 📋 执行顺序与依赖关系

```
Step 1 (WS基础设施) 
  │
  ├──► Step 2 (指标广播Task) ──► Step 6 (前端WS集成)
  │
  ├──► Step 3 (告警广播) ────────► Step 6
  │
  Step 4 (TopN API+前端) ◄── 独立可并行
  │
  Step 5 (时间范围API+前端) ◄── 独立可并行
  │
  Step 7 (PDF导出) ◄────────── 最后实现
```

---

## ✅ 验收标准

1. **WebSocket 连接**: 打开 Dashboard 后自动建立 WS 连接，断线后 5s 内自动重连
2. **实时数值**: CPU/内存/磁盘数值每 30s 自动更新（无需手动刷新页面）
3. **实时图表**: ECharts 趋势图收到新数据点后平滑滚动更新
4. **告警弹窗**: 新告警触发时，所有在线 Dashboard 右上角弹出 Toast 通知
5. **TopN 排行**: 支持按 CPU/内存/磁盘/负载排序的 Top10 列表
6. **时间范围**: 支持 1h/6h/24h/7d/30d 五档切换，图表数据随之变化
7. **PDF 导出**: 点击导出按钮后生成并下载监控报告 PDF 文件
