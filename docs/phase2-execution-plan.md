# AiOps 实时预警与监控 — Phase 2 可执行开发计划

**文档版本**: v1.0-EXEC  
**创建日期**: 2026-04-13  
**基于**: `realtime-alerting-monitoring-analysis-and-implementation.md` §15 分阶段实施路线图  
**前置条件**: Phase 1 全部完成 (monitoring 应用 + 规则引擎 + 异常检测 + 通知系统 + API + Dashboard)  
**目标**: 在 Phase 1 基础上，实现异常检测的深度集成、AI智能联动、参数可调优、历史回溯分析

---

## 📋 Phase 2 范围定义

### 本阶段交付物

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | **异常检测结果可视化标注** | Dashboard 趋势图上自动标记异常检测点 (ECharts markPoint) |
| 2 | **AI诊断自动联动机制** | 异常告警触发后 → 自动调用 LLM 进行根因分析 → 结果附入告警通知 |
| 3 | **检测算法参数调优界面** | Django Admin 中增加"算法配置"面板，支持运行时调整各检测器参数 |
| 4 | **历史异常回溯分析 API+前端** | 查询任意时间范围内的异常事件、展示对应指标曲线、AI诊断结论 |
| 5 | **性能优化** | 批量评估缓存、数据库索引优化、规则评估去重 |

### 不在本阶段范围

- Vue3 前端组件重写 (Phase 3)
- Grafana 数据源对接 (Phase 3)
- WebSocket 实时推送 (Phase 3)
- Prometheus 时序存储集成 (Phase 4)
- 邮件/短信/Slack 等多渠道完善 (Phase 4)
- 值班表与升级链路 (Phase 4)

---

## 🔧 Phase 2 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Phase 2 新增模块                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────┐    ┌──────────────────────────────────┐   │
│  │ W4-5: 可视化标注      │    │ W5-1: AI诊断自动联动              │   │
│  │                      │    │                                  │   │
│  │ AnomalyMarkerService │    │ AlertEvent.created               │   │
│  │ ┌──────────────────┐ │    │       ↓                         │   │
│  │ │ ECharts markPoint │ │    │ AnomalyAICallbackTask          │   │
│  │ │ 标注异常点        │◄┼────┼──► LLM.analyze(metrics)         │   │
│  │ │ 颜色/大小/tooltip │ │    │       ↓                         │   │
│  │ └──────────────────┘ │    │ AlertEvent.detail 更新           │   │
│  └──────────────────────┘    │       ↓                         │   │
│                               │ NotificationRouter.send()       │   │
│  ┌──────────────────────┐    └──────────────────────────────────┘   │
│  │ W5-2: 参数调优界面     │                                          │
│  │                      │                                          │
│  │ DetectorConfig Model │    ┌──────────────────────────────────┐   │
│  │ ┌──────────────────┐ │    │ W5-3: 历史回溯分析                │   │
│  │ │ zscore_threshold │ │    │                                  │   │
│  │ │ iqr_multiplier   │ │    │ GET /api/monitoring/anomalies/  │   │
│  │ │ ma_window_size   │ │    │ GET /api/monitoring/anomaly/ID/ │   │
│  │ │ roc_threshold    │ │    │ 前端: 异常时间线 + 曲线回放       │   │
│  │ │ composite_vote   │ │    │ + AI诊断报告                     │   │
│  │ └──────────────────┘ │    └──────────────────────────────────┘   │
│  └──────────────────────┘                                          │
│                                                                     │
│  ┌──────────────────────┐                                          │
│  │ W5-4: 性能优化        │                                          │
│  │                      │                                          │
│  │ • Redis 缓存评估结果  │                                          │
│  │ • DB Index 优化      │                                          │
│  │ • 批量查询减少 N+1   │                                          │
│  └──────────────────────┘                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 数据流 — AI诊断自动联动

```
RuleEvaluator.evaluate()
    ↓ 触发异常告警
AlertEvent.objects.create(status='firing', detail={anomaly_score, method_used, ...})
    ↓ signal / post_create hook
AnomalyAICallbackTask.delay(event_id)
    ↓ Celery异步任务
ai_ops.views.diagnose_server(server_id)  [复用现有逻辑]
    ↓ LLM返回分析结果
AlertEvent.detail['ai_diagnosis'] = {analysis, suggestions, confidence}
AlertEvent.save()
    ↓ 如果配置了 auto_notify_ai
send_alert_notifications(event_id)  [附带AI分析内容]
```

---

## 📁 文件变更清单 (共需新建/修改 9 个文件)

```
新建文件 (6个):
├── monitoring/
│   ├── anomaly_marker.py                ← W4-5: 异常点标记服务
│   ├── ai_callback.py                   ← W5-1: AI诊断自动联动 Celery Task
│   ├── models.py                        ← 新增 DetectorConfig / AnomalyHistory 模型
│   ├── admin.py                         ← W5-2: 算法参数调优 Admin UI
│   └── api/
│       ├── views.py                     ← W5-3: 新增异常回溯 API 端点
│       └── urls.py                      ← W5-3: 新增路由

修改文件 (3个):
├── templates/index.html                 ← W4-5: 图表嵌入异常标记
├── monitoring/engine/rule_evaluator.py  ← W5-1/W5-4: 触发AI回调 + 性能优化
├── monitoring/anomaly_detector.py       ← W5-2: 支持外部参数注入
```

---

## 🚀 详细执行步骤

---

## Step 1: 扩展数据模型 — models.py 新增模型

在现有 [monitoring/models.py](file:///d:/codes/aiops/monitoring/models.py) 末尾追加两个新模型：

### 1.1 DetectorConfig 模型 — 检测算法全局参数配置

```python
class DetectorConfig(models.Model):
    """异常检测算法全局参数配置 (单例模式)"""
    
    DETECTOR_CHOICES = [
        ('zscore', 'Z-Score 检测器'),
        ('iqr', 'IQR 四分位距检测器'),
        ('moving_avg', '移动平均检测器'),
        ('rate_of_change', '变化率检测器'),
        ('composite', '复合投票检测器'),
    ]
    
    detector_name = models.CharField("检测器名称", max_length=20, choices=DETECTOR_CHOICES, unique=True)
    is_enabled = models.BooleanField("是否启用", default=True)
    
    # 各检测器专属参数 (JSONField 统一存储)
    params = models.JSONField("参数配置", default=dict,
        help_text="zscore:{threshold:2.5} / iqr:{k:1.5} / moving_avg:{window:10,factor:2.0} / rate_of_change:{threshold:0.5,window:5} / composite:{vote_thr:0.6}")
    
    description = models.TextField("说明", blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = "检测器配置"
        verbose_name_plural = "检测器配置"
    
    def __str__(self):
        return f"{self.get_detector_name_display()} ({'启用' if self.is_enabled else '禁用'})"
    
    def get_param(self, key, default=None):
        return self.params.get(key, default)
```

### 1.2 AnomalyHistory 模型 — 历史异常记录

```python
class AnomalyHistory(models.Model):
    """异常检测历史记录 (用于回溯分析)"""
    
    SEVERITY_CHOICES = [
        ('high', '高度异常'),
        ('medium', '中度异常'),
        ('low', '轻度异常'),
    ]
    
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, related_name='anomaly_histories',
                               verbose_name="服务器", null=True, blank=True)
    metric_name = models.CharField("指标名", max_length=50)
    
    detected_at = models.DateTimeField("检测时间", db_index=True)
    severity = models.CharField("异常程度", max_length=10, choices=SEVERITY_CHOICES, default='medium')
    
    # 检测结果详情
    anomaly_score = models.FloatField("异常分数", default=0.0)
    method_used = models.CharField("使用的检测方法", max_length=30)
    raw_values = models.JSONField("原始数据序列", default=list)  # 最近N个数据点
    
    # 快照值
    current_value = models.FloatField("当前值")
    baseline_value = models.FloatField("基线值", null=True, blank=True)
    deviation_percent = models.FloatField("偏差百分比", null=True, blank=True)
    
    # 关联信息
    alert_event = models.OneToOneField(AlertEvent, on_delete=models.SET_NULL, null=True, blank=True,
                                       related_name='anomaly_history', verbose_name="关联告警")
    
    # AI 诊断结果 (异步填充)
    ai_diagnosis = models.TextField("AI诊断结论", blank=True, default='')
    ai_confidence = models.FloatField("AI置信度", null=True, blank=True)
    ai_analyzed_at = models.DateTimeField("AI分析时间", null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "异常历史"
        verbose_name_plural = "异常历史"
        ordering = ['-detected_at']
        indexes = [
            models.Index(fields=['server', 'detected_at'], name='idx_anomaly_server_time'),
            models.Index(fields=['metric_name', 'detected_at'], name='idx_anomaly_metric_time'),
            models.Index(fields=['severity'], name='idx_anomaly_severity'),
        ]
    
    @property
    def duration_minutes(self):
        if self.alert_event and self.alert_event.resolved_at:
            delta = self.alert_event.resolved_at - self.detected_at
            return int(delta.total_seconds() / 60)
        return None
```

---

## Step 2: 改造 anomaly_detector.py — 支持外部参数注入

修改现有的 `AnomalyDetector` 类，使其支持从 `DetectorConfig` 动态读取参数：

```python
# 在 AnomalyDetector 类中新增类方法:

@classmethod
def from_config(cls, method='auto'):
    """从数据库 DetectorConfig 创建检测器实例，使用用户配置的参数"""
    from .models import DetectorConfig
    
    det_map = {
        'zscore': ZScoreDetector,
        'iqr': IQRDetector,
        'moving_avg': MovingAvgDetector,
        'rate_of_change': RateOfChangeDetector,
        'composite': CompositeAnomalyDetector,
    }
    
    if method == 'auto':
        return cls(method='auto')  # 自动选择时走原有逻辑
    
    DetectorClass = det_map.get(method)
    if not DetectorClass:
        return cls(method='auto')
    
    # 从数据库读取配置参数
    config = DetectorConfig.objects.filter(detector_name=method, is_enabled=True).first()
    if config and config.params:
        return DetectorClass(**config.params)
    
    return DetectorClass()
```

同时修改各检测器的 `__init__` 方法，使其接受关键字参数：

```python
class ZScoreDetector(BaseDetector):
    method_name = "zscore"
    def __init__(self, threshold=2.5):  # 默认值作为 fallback
        self.threshold = threshold
    # ... detect() 方法中使用 self.threshold ...

class IQRDetector(BaseDetector):
    method_name = "iqr"
    def __init__(self, k=1.5):
        self.k = k
    # ... detect() 方法中使用 self.k ...

class MovingAvgDetector(BaseDetector):
    method_name = "moving_avg"
    def __init__(self, window=10, factor=2.0):
        self.window = window
        self.factor = factor
    # ... detect() 方法中使用 self.window, self.factor ...

class RateOfChangeDetector(BaseDetector):
    method_name = "rate_of_change"
    def __init__(self, threshold=0.5, window=5):
        self.threshold = threshold
        self.window = window
    # ... detect() 方法中使用 self.threshold, self.window ...

class CompositeAnomalyDetector(BaseDetector):
    method_name = "composite"
    def __init__(self, vote_thr=0.5, detectors=None):
        self.vote_thr = vote_thr
        # detectors 也从配置加载...
```

---

## Step 3: W4-5 — 异常点可视化标注服务

新建 [monitoring/anomaly_marker.py](file:///d:/codes/aiops/monitoring/anomaly_marker.py):

```python
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg, Max
from cmdb.models import ServerMetric
from monitoring.models import AnomalyHistory, AlertEvent
from monitoring.anomaly_detector import AnomalyDetector

logger = logging.getLogger(__name__)


class AnomalyMarkerService:
    """为 Dashboard 图表生成异常点标记数据 (ECharts markPoint 格式)"""

    @staticmethod
    def get_mark_points(server_id=None, metric_name='cpu_usage', days=1, limit=20):
        """
        获取指定服务器和指标的异常点标记
        
        Returns:
            list: ECharts markPoint.data 格式
            [
                {
                    'coord': [index, value],
                    'name': 'Z-Score异常',
                    'value': '异常分数: 0.95',
                    'itemStyle': {'color': '#ff4d4f'},
                    'symbol': 'pin',
                    'symbolSize': 40
                },
                ...
            ]
        """
        since = timezone.now() - timedelta(days=days)
        
        qs = AnomalyHistory.objects.filter(
            detected_at__gte=since,
            metric_name=metric_name,
        )
        
        if server_id:
            qs = qs.filter(server_id=server_id)
        
        histories = qs.select_related('alert_event', 'server')[:limit]
        
        color_map = {'high': '#ff4d4f', 'medium': '#faad14', 'low': '#52c41a'}
        
        marks = []
        for h in histories:
            marks.append({
                'coord': [h.detected_at.isoformat(), h.current_value],
                'name': f"{h.method_used}异常",
                'value': f"异常分数: {h.anomaly_score:.2f}",
                'itemStyle': {'color': color_map.get(h.severity, '#ff4d4f')},
                'symbol': 'pin' if h.severity == 'high' else 'circle',
                'symbolSize': 45 if h.severity == 'high' else 25,
                'label': {
                    'show': h.severity == 'high',
                    'formatter': f'{h.anomaly_score:.1f}',
                    'fontSize': 10,
                },
                'dataId': h.id,
            })
        
        return marks

    @staticmethod
    def get_anomaly_timeline(server_id=None, days=7):
        """
        获取异常时间线数据 (用于前端时间轴组件)
        
        Returns:
            dict: {
                'timeline': [...],
                'summary': {'total': N, 'by_severity': {...}, 'by_metric': {...}}
            }
        """
        since = timezone.now() - timedelta(days=days)
        
        qs = AnomalyHistory.objects.filter(detected_at__gte=since)
        if server_id:
            qs = qs.filter(server_id=server_id)
        
        histories = qs.select_related('server', 'alert_event').order_by('-detected_at')
        
        timeline = []
        for h in histories[:100]:
            timeline.append({
                'id': h.id,
                'time': h.detected_at.isoformat(),
                'server': h.server.hostname if h.server else 'Unknown',
                'server_id': h.server_id,
                'metric': h.metric_name,
                'severity': h.severity,
                'score': round(h.anomaly_score, 4),
                'method': h.method_used,
                'current_value': round(h.current_value, 2),
                'has_ai': bool(h.ai_diagnosis),
                'alert_status': h.alert_event.status if h.alert_event else None,
            })
        
        from django.db.models import Count
        summary = {
            'total': qs.count(),
            'by_severity': dict(qs.values_list('severity').annotate(cnt=Count('id')).values_list('severity', 'cnt')),
            'by_metric': dict(qs.values_list('metric_name').annotate(cnt=Count('id')).values_list('metric_name', 'cnt')),
        }
        
        return {'timeline': timeline, 'summary': summary}

    @staticmethod
    def get_anomaly_detail(anomaly_id):
        """
        获取单个异常的完整详情 (含前后数据曲线)
        
        Returns:
            dict: {
                'anomaly': {...},
                'series': {'times': [...], 'values': [...]},  // 前30个数据点
                'ai_diagnosis': {...}
            }
        """
        try:
            history = AnomalyHistory.objects.select_related(
                'server', 'alert_event', 'alert_event__rule'
            ).get(id=anomaly_id)
        except AnomalyHistory.DoesNotExist:
            return None
        
        # 获取异常发生前后的指标数据 (前30分钟到后10分钟)
        detected_at = history.detected_at
        window_start = detected_at - timedelta(minutes=30)
        window_end = detected_at + timedelta(minutes=10)
        
        metrics_qs = ServerMetric.objects.filter(
            server=history.server,
            collected_at__gte=window_start,
            collected_at__lte=window_end,
        ).order_by('collected_at')
        
        field_map = {
            'cpu_usage': 'cpu_usage',
            'mem_usage': 'mem_usage',
            'disk_usage': 'disk_usage',
            'load_1min': 'load_1min',
            'net_in': 'net_in',
            'net_out': 'net_out',
        }
        attr = field_map.get(history.metric_name, history.metric_name)
        
        series_data = {
            'times': [m.collected_at.isoformat() for m in metrics_qs],
            'values': [getattr(m, attr, 0) for m in metrics_qs],
        }
        
        result = {
            'anomaly': {
                'id': history.id,
                'server': history.server.hostname if history.server else '',
                'metric': history.metric_name,
                'detected_at': detected_at.isoformat(),
                'severity': history.severity,
                'score': round(history.anomaly_score, 4),
                'method': history.method_used,
                'current_value': round(history.current_value, 2),
                'baseline': round(history.baseline_value, 2) if history.baseline_value else None,
                'deviation_pct': round(history.deviation_percent, 2) if history.deviation_percent else None,
                'raw_values_sample': history.raw_values[-10:] if history.raw_values else [],
            },
            'series': series_data,
            'ai_diagnosis': {
                'content': history.ai_diagnosis,
                'confidence': history.ai_confidence,
                'analyzed_at': history.ai_analyzed_at.isoformat() if history.ai_analyzed_at else None,
            } if history.ai_diagnosis else None,
        }
        
        return result
```

---

## Step 4: W5-1 — AI诊断自动联动 Celery Task

新建 [monitoring/ai_callback.py](file:///d:/codes/aiops/monitoring/ai_callback.py):

```python
import json
import logging
from celery import shared_task
from django.utils import timezone
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def anomaly_ai_callback_task(self, event_id, server_id=None, metric_name='cpu_usage'):
    """
    异常告警触发后自动调用 AI 诊断
    
    流程:
    1. 根据 event_id 获取告警事件
    2. 收集该服务器最近20分钟的监控指标
    3. 调用 ai_ops 的诊断接口 (复用已有逻辑)
    4. 将 AI 分析结果写回 AlertEvent.detail 和 AnomalyHistory
    5. 可选: 发送包含 AI 分析的增强通知
    """
    from monitoring.models import AlertEvent, AnomalyHistory
    from cmdb.models import Server, ServerMetric
    from datetime import timedelta
    
    try:
        event = AlertEvent.objects.select_related('rule', 'server').get(id=event_id)
    except AlertEvent.DoesNotExist:
        logger.warning(f"[AICallback] 事件{event_id}不存在")
        return {'error': 'event_not_found'}
    
    if not server_id and event.server:
        server_id = event.server.id
    
    if not server_id:
        logger.warning(f"[AICallback] 事件{event_id}无关联服务器，跳过AI诊断")
        return {'error': 'no_server'}
    
    try:
        server = Server.objects.get(id=server_id)
    except Server.DoesNotExist:
        return {'error': 'server_not_found'}
    
    # 1. 收集最近20分钟的指标数据
    since = timezone.now() - timedelta(minutes=20)
    metrics = ServerMetric.objects.filter(
        server=server,
        collected_at__gte=since,
    ).order_by('-collected_at')[:20]
    
    if not metrics.exists():
        logger.info(f"[AICallback] 服务器{server.hostname}无最近指标数据，跳过")
        return {'error': 'no_metrics'}
    
    # 2. 构造诊断上下文
    context = _build_diagnostic_context(server, metrics, event, metric_name)
    
    # 3. 调用 AI 诊断
    analysis = _call_ai_diagnose(context)
    
    if not analysis:
        logger.warning(f"[AICallback] AI诊断返回空结果")
        return {'error': 'ai_empty_response'}
    
    # 4. 写回结果
    now = timezone.now()
    
    # 更新 AlertEvent.detail
    detail = event.detail or {}
    detail['ai_diagnosis'] = {
        'analysis': analysis.get('analysis', ''),
        'suggestions': analysis.get('suggestions', []),
        'confidence': analysis.get('confidence', 0),
        'analyzed_at': now.isoformat(),
        'model_used': analysis.get('model', 'default'),
    }
    event.detail = detail
    event.save(update_fields=['detail'])
    
    # 更新 AnomalyHistory (如果存在关联记录)
    anomaly_history = AnomalyHistory.objects.filter(alert_event=event).first()
    if anomaly_history:
        anomaly_history.ai_diagnosis = analysis.get('analysis', '')
        anomaly_history.ai_confidence = analysis.get('confidence')
        anomaly_history.ai_analyzed_at = now
        anomaly_history.save(update_fields=['ai_diagnosis', 'ai_confidence', 'ai_analyzed_at'])
    
    logger.info(f"[AICallback] 事件{event_id} AI诊断完成, 置信度={analysis.get('confidence', 0)}")
    
    return {
        'status': 'success',
        'event_id': event_id,
        'confidence': analysis.get('confidence', 0),
        'has_suggestions': bool(analysis.get('suggestions')),
    }
    
    except Exception as e:
        logger.error(f"[AICallback] 事件{event_id} AI诊断失败: {e}", exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (self.request.retries + 1))
        return {'error': str(e)}


def _build_diagnostic_context(server, metrics, event, metric_name):
    """构造发送给 AI 的诊断上下文"""
    
    latest = metrics.first()
    
    data_points = []
    for m in reversed(list(metrics)):
        data_points.append({
            'time': m.collected_at.strftime('%H:%M:%S'),
            'cpu': getattr(m, 'cpu_usage', 0),
            'mem': getattr(m, 'mem_usage', 0),
            'disk': getattr(m, 'disk_usage', 0),
            'load': getattr(m, 'load_1min', 0),
        })
    
    anomaly_info = event.detail or {}
    
    context = {
        'hostname': server.hostname,
        'ip': server.ip_address,
        'os': server.os_info or 'Unknown',
        'triggered_rule': event.rule.name if event.rule else 'Unknown',
        'triggered_metric': metric_name,
        'current_value': event.current_value,
        'threshold': event.threshold_value,
        'anomaly_score': anomaly_info.get('anomaly_score', 0),
        'method_used': anomaly_info.get('method_used', 'unknown'),
        'recent_metrics': data_points[-15:],  # 最近15个采样点
        'summary': {
            'avg_cpu': sum(d['cpu'] for d in data_points) / len(data_points) if data_points else 0,
            'avg_mem': sum(d['mem'] for d in data_points) / len(data_points) if data_points else 0,
            'peak_cpu': max((d['cpu'] for d in data_points), default=0),
            'peak_mem': max((d['mem'] for d in data_points), default=0),
            'trend': 'rising' if len(data_points) >= 2 and data_points[-1]['cpu'] > data_points[0]['cpu'] else 'stable',
        }
    }
    
    return context


def _call_ai_diagnose(context):
    """调用 AI 诊断服务 (复用 ai_ops 逻辑)"""
    try:
        from openai import OpenAI
        import os
        
        api_key = os.environ.get('OPENAI_API_KEY', '')
        base_url = os.environ.get('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        model = os.environ.get('AI_DIAGNOSE_MODEL', 'gpt-4o-mini')
        
        if not api_key:
            logger.warning("[AICallback] 未配置 OPENAI_API_KEY")
            return None
        
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        prompt = f"""你是一个专业的 AIOps 运维专家。请根据以下监控数据分析异常原因并给出处理建议。

## 服务器信息
- 主机名: {context['hostname']}
- IP地址: {context['ip']}
- 操作系统: {context['os']}

## 告警信息
- 触发规则: {context['triggered_rule']}
- 监控指标: {context['triggered_metric']}
- 当前值: {context['current_value']}
- 阈值/基线: {context.get('threshold', 'N/A')}
- 异常分数: {context['anomaly_score']}
- 检测方法: {context['method_used']}

## 近期指标趋势 (最近15个采样点)
{chr(10).join([f\"  [{d['time']}] CPU:{d['cpu']}% MEM:{d['mem']}% Load:{d['load']}\" for d in context['recent_metrics']])}

## 统计摘要
- 平均CPU: {context['summary']['avg_cpu']:.1f}%
- 平均内存: {context['summary']['avg_mem']:.1f}%
- 峰值CPU: {context['summary']['peak_cpu']:.1f}%
- 峰值内存: {context['summary']['peak_mem']:.1f}%
- 趋势判断: {context['summary']['trend']}

请以 JSON 格式返回分析结果:
{{
    "analysis": "根因分析文字描述(200字以内)",
    "suggestions": ["建议1", "建议2", "建议3"],
    "confidence": 0.0-1.0之间的置信度数值,
    "root_cause_category": "资源不足/配置错误/外部攻击/正常波动/其他",
    "urgency": "immediate/high/medium/low"
}}"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
            response_format={"type": "json_object"},
        )
        
        content = response.choices[0].message.content
        result = json.loads(content)
        
        return result
        
    except ImportError:
        logger.warning("[AICallback] openai 库未安装")
        return None
    except Exception as e:
        logger.error(f"[AICallback] AI调用异常: {e}")
        return None
```

---

## Step 5: 修改 rule_evaluator.py — 触发AI回调 + 记录AnomalyHistory

在 `_fire()` 方法和 `_eval_anomaly()` 处理器中加入：

```python
# 在 RuleEvaluator._fire() 方法末尾追加:

# === Phase 2: 异常类型告警触发 AI 回调 ===
if result.get('triggered') and self.rule.rule_type == 'anomaly':
    from monitoring.ai_callback import anomaly_ai_callback_task
    try:
        anomaly_ai_callback_task.delay(
            event_id=new_event.id,
            server_id=server.id,
            metric_name=self.rule.metric_name
        )
        logger.info(f"[RuleEngine] 已提交AI诊断任务: event={new_event.id}")
    except Exception as e:
        logger.error(f"[RuleEngine] 提交AI回调失败: {e}")

# === Phase 2: 记录 AnomalyHistory ===
if result.get('triggered'):
    try:
        from monitoring.models import AnomalyHistory
        score = result.get('anomaly_score', 0)
        sev = 'high' if score > 0.8 else 'medium' if score > 0.5 else 'low'
        AnomalyHistory.objects.create(
            server=server,
            metric_name=self.rule.metric_name,
            detected_at=timezone.now(),
            severity=sev,
            anomaly_score=score,
            method_used=result.get('method_used', 'unknown'),
            current_value=result.get('current_value', 0),
            baseline_value=result.get('baseline', result.get('threshold')),
            alert_event=new_event,
            raw_values=self._series(server, 30),
        )
    except Exception as e:
        logger.error(f"[RuleEngine] 记录AnomalyHistory失败: {e}")
```

---

## Step 6: W5-2 — Admin 参数调优 UI

在 [monitoring/admin.py](file:///d:/codes/aiops/monitoring/admin.py) 追加：

```python
@admin.register(DetectorConfig)
class DetectorConfigAdmin(admin.ModelAdmin):
    list_display = ['detector_name', 'is_enabled', 'description_short', 'updated_at']
    list_editable = ['is_enabled']
    list_filter = ['is_enabled', 'detector_name']
    
    fieldsets = (
        ('基本信息', {
            'fields': ('detector_name', 'is_enabled', 'description')
        }),
        ('参数配置 (JSON)', {
            'fields': ('params',),
            'classes': ('collapse',),
            'description': '''
            <b>各检测器参数格式:</b><br>
            • Z-Score: {"threshold": 2.5} &nbsp;← 阈值(标准差倍数)<br>
            • IQR: {"k": 1.5} &nbsp;← 四分位距倍数<br>
            • 移动平均: {"window": 10, "factor": 2.0}<br>
            • 变化率: {"threshold": 0.5, "window": 5}<br>
            • 复合投票: {"vote_thr": 0.6}
            ''',
        }),
    )
    
    def description_short(self, obj):
        return (obj.description or '')[:50]
    description_short.short_description = '说明'

@admin.register(AnomalyHistory)
class AnomalyHistoryAdmin(admin.ModelAdmin):
    list_display = ['server', 'metric_name', 'severity_badge', 'anomaly_score', 
                    'method_used', 'detected_at', 'has_ai']
    list_filter = ['severity', 'metric_name', 'method_used']
    search_fields = ['server__hostname', 'metric_name']
    date_hierarchy = 'detected_at'
    
    def has_add_permission(self, request): 
        return False  # 禁止手动添加，仅由系统自动生成
    
    def severity_badge(self, obj):
        colors = {'high':'red','medium':'orange','low':'blue'}
        return format_html('<span style="color:{}">{}</span>', 
                          colors.get(obj.severity,'gray'), obj.get_severity_display())
    severity_badge.short_description = '程度'
    
    def has_ai(self, obj):
        return bool(obj.ai_diagnosis)
    has_ai.boolean = True
    has_ai.short_description = 'AI已分析'
```

---

## Step 7: W5-3 — 历史回溯 API 端点

在 [monitoring/api/views.py](file:///d:/codes/aiops/monitoring/api/views.py) 追加：

```python
@login_required
@require_GET
def api_anomaly_timeline(request):
    """API: 获取异常时间线"""
    from monitoring.anomaly_marker import AnomalyMarkerService
    
    server_id = request.GET.get('server_id')
    days = int(request.GET.get('days', 7))
    
    if server_id:
        try:
            server_id = int(server_id)
        except ValueError:
            return JsonResponse({'code':1,'msg':'无效server_id'})
    
    data = AnomalyMarkerService.get_anomaly_timeline(server_id=server_id, days=days)
    return JsonResponse({'code':0,'data':data})

@login_required
@require_GET
def api_anomaly_detail(request, anomaly_id):
    """API: 获取单个异常详情 (含曲线+AI诊断)"""
    from monitoring.anomaly_marker import AnomalyMarkerService
    
    data = AnomalyMarkerService.get_anomaly_detail(anomaly_id)
    if not data:
        return JsonResponse({'code':1,'msg':'异常记录不存在'})
    return JsonResponse({'code':0,'data':data})

@login_required
@require_GET
def api_anomaly_markpoints(request):
    """API: 获取图表异常点标记 (ECharts格式)"""
    from monitoring.anomaly_marker import AnomalyMarkerService
    
    server_id = request.GET.get('server_id')
    metric_name = request.GET.get('metric_name', 'cpu_usage')
    days = int(request.GET.get('days', 1))
    
    if server_id:
        try:
            server_id = int(server_id)
        except ValueError:
            return JsonResponse({'code':1,'msg':'无效server_id'})
    
    marks = AnomalyMarkerService.get_mark_points(
        server_id=server_id, metric_name=metric_name, days=days
    )
    return JsonResponse({'code':0,'data':{'markPoints':marks}})
```

在 [monitoring/api/urls.py](file:///d:/codes/aiops/monitoring/api/urls.py) 追加路由：

```python
path('anomalies/timeline/', views.api_anomaly_timeline, name='api_anomaly_timeline'),
path('anomalies/markpoints/', views.api_anomaly_markpoints, name='api_anomaly_markpoints'),
path('anomalies/<int:anomaly_id>/', views.api_anomaly_detail, name='api_anomaly_detail'),
```

---

## Step 8: W4-5 — Dashboard 图表异常标记

在 [templates/index.html](file:///d:/codes/aiops/templates/index.html) 的 ECharts 初始化代码中追加：

### 8.1 在 chartTrend.setOption 之后添加 markPoint：

```javascript
// 在趋势图初始化后，异步加载异常标记
fetch('/api/monitoring/anomalies/markpoints/?metric_name=cpu_usage&days=1'
      + (serverId ? '&server_id='+serverId : ''))
    .then(r => r.json())
    .then(resp => {
        if (resp.code === 0 && resp.data.markPoints.length > 0) {
            const option = chartTrend.getOption();
            option.series[0].markPoint = {
                data: resp.data.markPoints.map(m => ({
                    coord: m.coord,
                    name: m.name,
                    value: m.value,
                    itemStyle: m.itemStyle,
                    symbol: m.symbol || 'pin',
                    symbolSize: m.symbolSize || 40,
                    label: m.label || { show: false }
                })),
                animationDelay: 500
            };
            // 同时给 Memory 序列也加上标记
            if (option.series[1]) {
                option.series[1].markPoint = option.series[0].markPoint;
            }
            chartTrend.setOption(option);
        }
    });
```

### 8.2 新增异常时间线侧边栏组件：

在 Dashboard HTML 中（告警面板下方）插入：

```html
<!-- 异常时间线 (Phase 2 新增) -->
<div class="row mt-3">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">
                    <i class="fas fa-history text-warning"></i> 异常检测时间线
                    <span id="anomaly-count" class="badge badge-warning ml-2">0</span>
                </h5>
                <div>
                    <select id="anomaly-days" class="form-control form-control-sm d-inline-block" style="width:auto;">
                        <option value="1">近1天</option>
                        <option value="7" selected>近7天</option>
                        <option value="30">近30天</option>
                    </select>
                </div>
            </div>
            <div class="card-body p-0" style="max-height:400px; overflow-y:auto;">
                <div id="anomaly-timeline" class="list-group list-group-flush">
                    <div class="text-center text-muted py-3">加载中...</div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- 异常详情弹窗 -->
<div class="modal fade" id="anomalyDetailModal" tabindex="-1">
    <div class="modal-dialog modal-lg">
        <div class="modal-content">
            <div class="modal-header bg-warning">
                <h5 class="modal-title"><i class="fas fa-exclamation-triangle"></i> 异常详情</h5>
                <button type="button" class="close" data-dismiss="modal"><span>&times;</span></button>
            </div>
            <div class="modal-body">
                <div id="anomaly-detail-content">加载中...</div>
                <div id="anomaly-chart-container" style="height:250px;"></div>
            </div>
            <div class="modal-footer" id="anomaly-detail-footer"></div>
        </div>
    </div>
</div>
```

### 8.3 对应 JavaScript 逻辑：

```javascript
function loadAnomalyTimeline(days) {
    fetch('/api/monitoring/anomalies/timeline/?days=' + days
          + (serverId ? '&server_id='+serverId : ''))
        .then(r => r.json())
        .then(resp => {
            const container = document.getElementById('anomaly-timeline');
            const countEl = document.getElementById('anomaly-count');
            
            if (resp.code !== 0 || !resp.data.timeline.length) {
                container.innerHTML = '<div class="text-center text-muted py-3"><i class="fas fa-check-circle"></i> 近'+days+'天无异常检测记录</div>';
                countEl.textContent = '0';
                return;
            }
            
            countEl.textContent = resp.data.summary.total;
            
            const sevIcons = {'high':'fa-fire text-danger','medium':'fa-exclamation-triangle text-warning','low':'fa-info-circle text-info'};
            const sevBg = {'high':'bg-danger-subtle','medium':'bg-warning-subtle','low':'bg-info-subtle'};
            
            container.innerHTML = resp.data.timeline.map(a => `
                <div class="list-group-item list-group-item-action ${sevBg[a.severity]}" style="cursor:pointer;" onclick="showAnomalyDetail(${a.id})">
                    <div class="d-flex w-100 justify-content-between">
                        <h6 class="mb-1">
                            <i class="fas ${sevIcons[a.severity]}"></i>
                            ${esc(a.server)} - ${a.metric}
                            ${a.has_ai ? '<i class="fas fa-robot text-primary ml-1" title="已AI分析"></i>' : ''}
                        </h6>
                        <small>${timeAgo(a.time)}</small>
                    </div>
                    <p class="mb-1 small">${a.method} | 分数: ${a.score} | 当前值: ${a.current_value}</p>
                    ${a.alert_status ? `<small><span class="badge badge-secondary">${a.alert_status}</span></small>` : ''}
                </div>
            `).join('');
        });
}

function showAnomalyDetail(id) {
    $('#anomalyDetailModal').modal('show');
    document.getElementById('anomaly-detail-content').innerHTML = '<div class="text-center py-3"><div class="spinner-border"></div></div>';
    
    fetch('/api/monitoring/anomalies/' + id + '/')
        .then(r => r.json())
        .then(resp => {
            if (resp.code !== 0) {
                document.getElementById('anomaly-detail-content').innerHTML = '<div class="alert alert-danger">加载失败</div>';
                return;
            }
            
            const d = resp.data.anomaly;
            const ai = resp.data.ai_diagnosis;
            
            let html = `
                <div class="row mb-3">
                    <div class="col-md-6">
                        <table class="table table-sm table-borderless">
                            <tr><td class="font-weight-bold text-muted w-40%">服务器:</td><td>${d.server}</td></tr>
                            <tr><td class="font-weight-bold text-muted">指标:</td><td>${d.metric}</td></tr>
                            <tr><td class="font-weight-bold text-muted">检测时间:</td><td>${d.detected_at}</td></tr>
                            <tr><td class="font-weight-bold text-muted">检测方法:</td><td>${d.method}</td></tr>
                            <tr><td class="font-weight-bold text-muted">当前值:</td><td><strong>${d.current_value}</strong></td></tr>
                            <tr><td class="font-weight-bold text-muted">基线值:</td><td>${d.baseline ?? '-'}</td></tr>
                            <tr><td class="font-weight-bold text-muted">偏差:</td><td>${d.deviation_pct != null ? d.deviation_pct+'%' : '-'}</td></tr>
                            <tr><td class="font-weight-bold text-muted">异常分数:</td><td><span class="badge badge-${d.score>0.8?'danger':d.score>0.5?'warning':'info'}">${d.score}</span></td></tr>
                        </table>
                    </div>
                    <div class="col-md-6">
                        <div id="anomaly-detail-chart" style="height:180px;"></div>
                    </div>
                </div>`;
            
            if (ai && ai.content) {
                html += `
                    <hr>
                    <div class="alert alert-primary">
                        <h6><i class="fas fa-robot"></i> AI 诊断结论 
                            <small class="text-muted">(置信度: ${(ai.confidence*100).toFixed(0)}%)</small>
                        </h6>
                        <pre class="mb-0 small" style="white-space:pre-wrap;">${esc(ai.content)}</pre>
                    </div>`;
            } else {
                html += `<hr><div class="text-muted text-center py-2"><small>暂无AI诊断结果</small></div>`;
            }
            
            document.getElementById('anomaly-detail-content').innerHTML = html;
            
            // 渲染迷你曲线图
            if (resp.data.series.times.length > 0) {
                renderAnomalyChart(resp.data.series);
            }
        });
}

function renderAnomalyChart(seriesData) {
    const dom = document.getElementById('anomaly-detail-chart');
    if (!dom || !echarts) return;
    
    const chart = echarts.init(dom);
    chart.setOption({
        grid: { left: 50, right: 20, top: 20, bottom: 30 },
        xAxis: { type: 'category', data: seriesData.times.map(t => t.substring(11,19)), axisLabel: {fontSize:10} },
        yAxis: { type: 'value', splitLine: {lineStyle:{type:'dashed'}} },
        series: [{
            type: 'line', smooth: true, data: seriesData.values,
            lineStyle: {color:'#1890ff', width:2},
            areaStyle: {opacity:0.1, color:'#1890ff'},
            markLine: {
                data: [{type:'average', name:'均值'}],
                label: {formatter:'均值: {c}'}
            }
        }]
    });
}

document.addEventListener('DOMContentLoaded', function(){
    loadAnomalyTimeline(7);
    document.getElementById('anomaly-days').addEventListener('change', function(){
        loadAnomalyTimeline(this.value);
    });
});
```

---

## Step 9: W5-4 — 性能优化

### 9.1 数据库迁移新增索引

确保以下索引已在 models.py 中定义 (Step 1 已包含)：
- `AnomalyHistory`: `(server, detected_at)`, `(metric_name, detected_at)`, `(severity)`
- `AlertEvent`: `(status, fired_at)` — Phase 1 已有

### 9.2 规则评估批量优化

在 `rule_evaluator.py` 的 `evaluate_all()` 中：

```python
@classmethod
def evaluate_all(cls):
    results = {'evaluated': 0, 'fired': 0, 'errors': []}
    
    rules = list(AlertRule.objects.filter(status='enabled').select_related('created_by'))
    servers_cache = {}  # 服务器缓存
    
    for rule in rules:
        try:
            evaluator = cls(rule)
            targets = evaluator._get_targets()
            
            for server in targets:
                cache_key = f"rule_eval_{rule.id}_{server.id}"
                
                # 冷却期检查 (Redis缓存)
                from django.core.cache import cache
                if cache.get(cache_key):
                    continue  # 跳过冷却中的目标
                
                fired, _ = evaluator.evaluate(server_id=server.id)
                results['evaluated'] += 1
                
                if fired:
                    results['fired'] += 1
                    # 设置冷却期缓存
                    cache.set(cache_key, True, timeout=rule.cooldown_seconds)
                    
        except Exception as e:
            logger.error(f"[RuleEngine] 规则{rule.id}异常: {e}")
            results['errors'].append({'rule_id': rule.id, 'error': str(e)})
    
    return results
```

### 9.3 查询优化 — 避免 N+1

所有 API 端点均使用 `select_related` / `prefetch_related` 减少查询次数。

---

## ✅ 验证检查清单

### V1: 数据库迁移
```bash
python manage.py makemigrations monitoring
python manage.py migrate
```
预期输出：新增 `DetectorConfig`, `AnomalyHistory` 两张表

### V2: Admin 后台验证
- 访问 `/admin/monitoring/detectorconfig/` → 应看到5条预置检测器配置记录
- 访问 `/admin/monitoring/anomalyhistory/` → 初始为空 (由系统自动生成)

### V3: API 接口验证
```bash
# 异常时间线
GET /api/monitoring/anomalies/timeline/?days=7
# 预期: {"code":0,"data":{"timeline":[],"summary":{"total":0,...}}}

# 异常点标记
GET /api/monitoring/anomalies/markpoints/?metric_name=cpu_usage&days=1
# 预期: {"code":0,"data":{"markPoints":[]}}

# 单个异常详情
GET /api/monitoring/anomalies/1/
# 预期: {"code":1,"msg":"异常记录不存在"} 或 详情数据
```

### V4: 功能联调测试
1. 创建一条 `anomaly` 类型的 AlertRule
2. 启动 `python manage.py evaluate_rules`
3. 触发异常后检查：
   - [ ] `AnomalyHistory` 表有新记录
   - [ ] `AlertEvent.detail` 包含 `ai_diagnosis` 字段 (需配置 OPENAI_API_KEY)
   - [ ] Dashboard 图表出现红色 pin 标记
   - [ ] 异常时间线显示新记录

### V5: 参数调优测试
1. 进入 Admin → 检测器配置
2. 修改 Z-Score threshold 从 2.5 → 3.0
3. 再次触发规则评估 → 敏感度应降低

---

## 📊 Phase 2 完成标准

| 标准 | 验收条件 |
|------|---------|
| **异常可视化** | Dashboard 趋势图能正确显示异常点 pin 标记 |
| **AI联动** | 异常告警触发后 ≤2分钟内自动完成AI诊断并写入 |
| **参数可调** | Admin后台能修改各检测器参数并即时生效 |
| **历史回溯** | 能查看任意时间段内的异常记录及详细曲线 |
| **性能达标** | 100台服务器全量评估耗时 < 30秒 |

---

## ⏰ 时间节点参考

| 步骤 | 内容 | 预计工时 |
|------|------|---------|
| Step 1 | 数据模型扩展 (DetectorConfig + AnomalyHistory) | 0.5h |
| Step 2 | anomaly_detector.py 参数注入改造 | 0.5h |
| Step 3 | anomaly_marker.py 可视化标注服务 | 1h |
| Step 4 | ai_callback.py AI联动 Celery Task | 1.5h |
| Step 5 | rule_evaluator.py 集成回调+历史记录 | 0.5h |
| Step 6 | Admin 参数调优 UI | 0.5h |
| Step 7 | 历史回溯 API 端点 | 0.5h |
| Step 8 | Dashboard 图表标记+时间线前端 | 1.5h |
| Step 9 | 性能优化 (缓存/索引/批量) | 0.5h |
| **合计** | | **~7h** |
