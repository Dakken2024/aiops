# AiOps 实时预警与监控 — Phase 1 可执行开发计划

**文档版本**: v1.0-EXEC  
**创建日期**: 2026-04-13  
**基于**: `realtime-alerting-monitoring-analysis-and-implementation.md`  
**目标**: 从零构建基础告警能力，让项目具备可配置的实时预警系统

---

## 📋 Phase 1 范围定义

### 本阶段交付物

| # | 交付物 | 说明 |
|---|--------|------|
| 1 | **monitoring Django 应用** | 完整的 models/admin/apps/migrations |
| 2 | **规则引擎** | 支持6种规则类型的评估器 (threshold/baseline/trend/composite/absence/anomaly) |
| 3 | **异常检测算法库** | ZScore/IQR/MovingAvg/RateOfChange/Composite 5种检测器 |
| 4 | **多渠道通知中心** | 钉钉/企微/邮件/Slack/Webhook + Celery重试 |
| 5 | **REST API** | 规则CRUD + 告警事件管理 + 统计接口 |
| 6 | **Celery调度任务** | 规则自动评估定时任务 |
| 7 | **Dashboard增强** | 告警面板嵌入现有仪表盘 |

### 不在本阶段范围

- Prometheus/TimescaleDB 时序数据库集成 (Phase 2)
- Grafana 可视化对接 (Phase 2)
- Vue3 前端组件重写 (Phase 3)
- WebSocket 实时推送 (Phase 3)

---

## 🔧 执行前准备

### Step 0: 安装新增依赖

```bash
# 在项目根目录 d:\codes\aiops\ 下执行
pip install scikit-learn statsmodels numpy
```

修改 [requirements.txt](file:///d:/codes/aiops/requirements.txt)，追加以下内容：

```txt
scikit-learn>=1.3.0
statsmodels>=0.14.0
numpy>=1.24.0
```

---

## 📁 文件创建清单 (共需新建/修改 12 个文件)

```
新建文件 (10个):
├── monitoring/
│   ├── __init__.py
│   ├── apps.py
│   ├── models.py                    ← 核心数据模型
│   ├── admin.py                     ← Admin后台管理
│   ├── engine/
│   │   ├── __init__.py
│   │   └── rule_evaluator.py        ← 规则引擎核心
│   ├── anomaly_detector.py          ← 异常检测算法库
│   ├── notification/
│   │   ├── __init__.py
│   │   └── channel_manager.py       ← 多渠道通知中心
│   ├── api/
│   │   ├── __init__.py
│   │   ├── views.py                 ← REST API视图
│   │   └── urls.py                  ← API路由
│   └── management/
│       └── commands/
│           └── evaluate_rules.py    ← Celery定时任务
│   └── migrations/
│       └── __init__.py              ← 迁移目录初始化

修改文件 (3个):
├── ops_platform/settings.py         ← 注册monitoring应用 + 新增日志配置
├── ops_platform/urls.py             ← 添加监控路由
├── templates/index.html             ← Dashboard嵌入告警面板
```

---

## 🚀 详细执行步骤

### Step 1: 创建 monitoring 应用骨架

#### 1.1 创建目录结构

在 `d:\codes\aiops\` 下执行以下命令：

```bash
mkdir monitoring
mkdir monitoring\engine
mkdir monitoring\notification
mkdir monitoring\api
mkdir monitoring\management\commands
mkdir monitoring\migrations
```

#### 1.2 创建 `monitoring/__init__.py`

```python
# monitoring/__init__.py
default_app_config = 'monitoring.apps.MonitoringConfig'
```

#### 1.3 创建 `monitoring/apps.py`

```python
# monitoring/apps.py
from django.apps import AppConfig


class MonitoringConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'monitoring'
    verbose_name = '智能监控告警'

    def ready(self):
        pass
```

#### 1.4 创建 `monitoring/migrations/__init__.py`

```python
# monitoring/migrations/__init__.py
```

---

### Step 2: 核心数据模型 — `monitoring/models.py`

完整代码写入 `d:\codes\aiops\monitoring\models.py`：

```python
# monitoring/models.py
import json
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class AlertRule(models.Model):
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
        ('threshold', '静态阈值'),
        ('baseline', '动态基线'),
        ('trend', '趋势检测'),
        ('composite', '复合条件'),
        ('absence', '消失检测'),
        ('anomaly', '异常检测'),
    ]

    name = models.CharField("规则名称", max_length=200, unique=True)
    description = models.TextField("规则描述", blank=True)
    rule_type = models.CharField("规则类型", max_length=20, choices=RULE_TYPE_CHOICES, default='threshold')
    severity = models.CharField("严重级别", max_length=10, choices=SEVERITY_CHOICES, default='P1')
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='enabled')

    target_all = models.BooleanField("应用于所有服务器", default=True)
    metric_name = models.CharField("监控指标", max_length=50, default='cpu_usage',
        help_text="cpu_usage / mem_usage / disk_usage / load_1min / net_in / net_out")
    condition_config = models.JSONField("条件配置", default=dict,
        help_text="静态阈值:{'operator':'gt','value':90} / 动态基线:{'multiplier':1.5}")

    evaluate_interval = models.PositiveIntegerField("评估间隔(秒)", default=60)
    lookback_window = models.PositiveIntegerField("回溯窗口(个)", default=5)
    cooldown_seconds = models.PositiveIntegerField("冷却时间(秒)", default=300,
        help_text="同一目标触发后N秒内不再重复触发")
    max_alerts_per_hour = models.PositiveIntegerField("每小时最大告警数", default=10)

    notify_channels = models.JSONField("通知渠道", default=list, help_text="['dingtalk','wechat','email']")
    notify_template = models.TextField("通知模板", blank=True, default="")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_triggered_at = models.DateTimeField("最后触发时间", null=True, blank=True)
    trigger_count = models.PositiveIntegerField("累计触发次数", default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "预警规则"
        verbose_name_plural = "预警规则"
        indexes = [
            models.Index(fields=['status', 'rule_type']),
            models.Index(fields=['severity']),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.name}"


class AlertEvent(models.Model):
    STATUS_CHOICES = [
        ('firing', '触发中'), ('resolved', '已恢复'),
        ('acknowledged', '已确认'), ('silenced', '已静默'),
    ]

    rule = models.ForeignKey(AlertRule, on_delete=models.CASCADE, related_name='events')
    server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True, related_name='alert_events')

    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES, default='firing')
    severity = models.CharField("级别", max_length=10)
    metric_name = models.CharField("指标名", max_length=50)
    current_value = models.FloatField("当前值")
    threshold_value = models.FloatField("阈值/基线", null=True, blank=True)
    message = models.TextField("告警消息", default="")
    detail = models.JSONField("详细信息", default=dict)

    fired_at = models.DateTimeField("触发时间", auto_now_add=True)
    resolved_at = models.DateTimeField("恢复时间", null=True, blank=True)
    acknowledged_at = models.DateTimeField("确认时间", null=True, blank=True)
    acknowledged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    notification_log = models.JSONField("通知记录", default=list)

    class Meta:
        ordering = ['-fired_at']
        verbose_name = "告警事件"
        indexes = [
            models.Index(fields=['status', '-fired_at']),
            models.Index(fields=['server', 'status']),
        ]

    @property
    def duration(self):
        end = self.resolved_at or timezone.now()
        return (end - self.fired_at).total_seconds()


class AlertSilenceRule(models.Model):
    name = models.CharField("静默名称", max_length=200)
    match_severity = models.CharField("匹配级别", max_length=10, blank=True, default='')
    match_rule_name = models.CharField("匹配规则", max_length=200, blank=True, default='')
    match_server = models.ForeignKey('cmdb.Server', on_delete=models.CASCADE, null=True, blank=True)
    start_time = models.DateTimeField("开始时间")
    end_time = models.DateTimeField("结束时间")
    comment = models.TextField("备注", blank=True)
    is_active = models.BooleanField("生效中", default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "静默规则"


class NotificationLog(models.Model):
    CHANNEL_CHOICES = [('dingtalk','钉钉'),('wechat','企业微信'),('email','邮件'),('slack','Slack'),('webhook','Webhook')]
    STATUS_CHOICES = [('sent','已发送'),('failed','发送失败'),('retrying','重试中')]

    alert_event = models.ForeignKey(AlertEvent, on_delete=models.CASCADE, related_name='notify_logs')
    channel = models.CharField("渠道", max_length=20, choices=CHANNEL_CHOICES)
    status = models.CharField("状态", max_length=20, choices=STATUS_CHOICES)
    recipient = models.JSONField("接收者信息", default=dict)
    content_summary = models.TextField("内容摘要", blank=True)
    error_message = models.TextField("错误信息", blank=True)
    retry_count = models.PositiveIntegerField("重试次数", default=0)
    sent_at = models.DateTimeField("发送时间", auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = "通知记录"
```

---

### Step 3: Django Admin — `monitoring/admin.py`

```python
# monitoring/admin.py
from django.contrib import admin
from .models import AlertRule, AlertEvent, AlertSilenceRule, NotificationLog


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'rule_type', 'severity', 'status', 'metric_name',
                    'trigger_count', 'last_triggered_at']
    list_filter = ['status', 'severity', 'rule_type']
    search_fields = ['name', 'description']
    readonly_fields = ['trigger_count', 'last_triggered_at']

    fieldsets = (
        ('基本信息', {'fields': ('name','description','rule_type','severity','status')}),
        ('目标配置', {'fields': ('target_all','metric_name','condition_config')}),
        ('评估参数', {'fields': ('evaluate_interval','lookback_window','cooldown_seconds','max_alerts_per_hour')}),
        ('通知', {'fields': ('notify_channels','notify_template')}),
        ('元数据', {'fields': ('created_by','trigger_count','last_triggered_at','created_at','updated_at'),
                   'classes': ('collapse',)}),
    )


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display = ['id', 'rule', 'server', 'severity', 'status', 'current_value', 'fired_at']
    list_filter = ['status', 'severity']
    search_fields = ['message', 'server__hostname', 'rule__name']
    readonly_fields = ['fired_at', 'notification_log']
    def has_add_permission(self, request): return False


@admin.register(AlertSilenceRule)
class AlertSilenceRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'start_time', 'end_time']


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ['channel', 'status', 'alert_event', 'retry_count', 'sent_at']
    list_filter = ['channel', 'status']
    def has_add_permission(self, request): return False
```

---

### Step 4: 规则引擎 — `monitoring/engine/rule_evaluator.py`

#### 4.1 创建 `monitoring/engine/__init__.py` (空文件)

#### 4.2 创建 `monitoring/engine/rule_evaluator.py`

```python
# monitoring/engine/rule_evaluator.py
import logging
import statistics
from datetime import timedelta
from django.utils import timezone
from django.db import models as dj_models
from monitoring.models import AlertRule, AlertEvent, AlertSilenceRule

logger = logging.getLogger(__name__)

METRIC_FIELD_MAP = {
    'cpu_usage':'cpu_usage','mem_usage':'mem_usage','disk_usage':'disk_usage',
    'load_1min':'load_1min','net_in':'net_in','net_out':'net_out',
    'disk_read_rate':'disk_read_rate','disk_write_rate':'disk_write_rate',
}


class RuleEvaluator:
    HANDLER_MAP = {}

    @classmethod
    def register(cls, rule_type):
        def decorator(func):
            cls.HANDLER_MAP[rule_type] = func
            return func
        return decorator

    @classmethod
    def evaluate_all(cls):
        results = {'evaluated':0,'fired':0,'errors':[]}
        for rule in AlertRule.objects.filter(status='enabled'):
            try:
                evaluator = cls(rule)
                fired, _ = evaluator.evaluate()
                results['evaluated'] += 1
                if fired: results['fired'] += 1
            except Exception as e:
                logger.error(f"[RuleEngine] 规则{rule.id}异常: {e}")
                results['errors'].append({'rule_id':rule.id,'error':str(e)})
        return results

    def __init__(self, rule):
        self.rule = rule
        self.condition = rule.condition_config or {}
        self.handler = self.HANDLER_MAP.get(rule.rule_type)

    def evaluate(self, server_id=None):
        if not self.handler:
            return False, {'reason': f'unknown_rule_type:{self.rule.rule_type}'}
        servers = self._get_targets(server_id)
        any_fired = False
        for server in servers:
            try:
                result = self.handler(self, server)
                if result.get('triggered'):
                    self._fire(server, result)
                    any_fired = True
            except Exception as e:
                logger.error(f"[RuleEngine] {server.hostname}: {e}")
        return any_fired, {}

    def _get_targets(self, sid):
        from cmdb.models import Server
        q = Server.objects.filter(status='Running')
        if sid: q = q.filter(id=sid)
        elif not self.rule.target_all:
            tids = list(self.rule.target_servers.values_list('id',flat=True))
            gids = list(self.rule.target_groups.values_list('id',flat=True))
            if tids: q = q.filter(id__in=tids)
            if gids: q = q.filter(group_id__in=gids)
        return q.distinct()

    def _latest(self, server):
        from cmdb.models import ServerMetric
        field = METRIC_FIELD_MAP.get(self.rule.metric_name,'cpu_usage')
        try:
            m = ServerMetric.objects.filter(server=server).latest('created_at')
            return getattr(m,field), m
        except Exception:
            return None,None

    def _series(self, server, limit=30):
        from cmdb.models import ServerMetric
        field = METRIC_FIELD_MAP.get(self.rule.metric_name,'cpu_usage')
        qs = ServerMetric.objects.filter(server=server).order_by('-created_at')[:limit]
        return [getattr(m,field) for m in reversed(qs)]

    def _fire(self, server, result):
        # 冷却检查
        if AlertEvent.objects.filter(rule=self.rule,server=server,status='firing',
            fired_at__gte=timezone.now()-timedelta(seconds=self.rule.cooldown_seconds)).exists():
            return
        # 静默检查
        now = timezone.now()
        if AlertSilenceRule.objects.filter(is_active=True,start_time__lte=now,end_time__gte=now
            ).filter(dj_models.Q(match_server=server)|dj_models.Q(match_server__isnull=True)
            ).filter(dj_models.Q(match_severity='')|dj_models.Q(match_severity=self.rule.severity)
            ).exists():
            return
        # 频率限制
        hour_ago = now - timedelta(hours=1)
        if AlertEvent.objects.filter(rule=self.rule,server=server,fired_at__gte=hour_ago
            ).count() >= self.rule.max_alerts_per_hour:
            return

        event = AlertEvent.objects.create(
            rule=self.rule, server=server, severity=self.rule.severity,
            metric_name=self.rule.metric_name,
            current_value=result.get('current_value',0),
            threshold_value=result.get('threshold') or result.get('baseline'),
            message=self._msg(server,result), detail=result,
        )
        AlertRule.objects.filter(id=self.rule.id).update(
            last_triggered_at=now, trigger_count=dj_models.F('trigger_count')+1)
        from monitoring.notification.channel_manager import send_alert_notifications
        send_alert_notifications.delay(event.id)
        logger.warning(f"ALERT [{self.rule.severity}] {self.rule.name} -> {server.hostname}")

    def _msg(self, server, r):
        t = {'threshold':f"{server.hostname} {self.rule.metric_name}={r.get('current_value','?')} "
              f"{self.condition.get('operator','>')} {self.condition.get('value','?')}",
             'baseline':f"{server.hostname} {self.rule.metric_name}={r.get('current_value','?')} 超基线",
             'trend':f"{server.hostname} {self.rule.metric_name} 持续{self.condition.get('direction','up')}趋势",
             'composite':f"{server.hostname} 复合条件触发",
             'absence':f"{server.hostname} {r.get('last_report_minutes_ago','?')}分钟未上报",
             'anomaly':f"{server.hostname} 异常(分数={r.get('anomaly_score','?')})"}
        return t.get(self.rule.rule_type, f"{server.hostname} 告警")


@RuleEvaluator.register('threshold')
def _eval_threshold(self, s):
    val,_ = self._latest(s)
    if val is None: return {'triggered':False,'reason':'no_data'}
    op = self.condition.get('operator','gt')
    thr = self.condition.get('value',0)
    ok = val > thr if op=='gt' else val >= thr if op=='gte' else val < thr if op=='lt' else val <= thr
    return {'triggered':ok,'current_value':round(val,2),'threshold':thr}

@RuleEvaluator.register('baseline')
def _eval_baseline(self, s):
    hrs = self.condition.get('lookback_hours',168)
    mul = self.condition.get('multiplier',1.5)
    field = METRIC_FIELD_MAP.get(self.rule.metric_name,'cpu_usage')
    from cmdb.models import ServerMetric
    qs = ServerMetric.objects.filter(server=s,
        created_at__range=(timezone.now()-timedelta(hours=hrs),timezone.now()))
    vals = [getattr(m,field) for m in qs]
    if len(vals)<10: return {'triggered':False,'reason':f'history({len(vals)})'}
    base = statistics.mean(vals)*mul
    cv,_ = self._latest(s)
    if cv is None: return {'triggered':False}
    return {'triggered':cv>base,'current_value':round(cv,2),'baseline':round(base,2)}

@RuleEvaluator.register('trend')
def _eval_trend(self, s):
    w = self.condition.get('window',5)
    d = self.condition.get('direction','up')
    ct = self.condition.get('change_threshold',1)
    vals = self._series(s,w+1)
    if len(vals)<w+1: return {'triggered':False}
    changes = [vals[i]-vals[i-1] for i in range(1,len(vals))]
    ok = all(c>ct for c in changes) if d=='up' else all(c<-ct for c in changes)
    slope = (vals[-1]-vals[0])/len(vals) if len(vals)>1 else 0
    return {'triggered':bool(ok),'direction':d,'slope':round(slope,4)}

@RuleEvaluator.register('composite')
def _eval_composite(self, s):
    logic = self.condition.get('logic','AND')
    subs = self.condition.get('conditions',[])
    rlist = []
    for sub in subs:
        cv,_ = self._latest(s)
        if cv is None: rlist.append(False); continue
        op = sub.get('operator','gt'); v = sub.get('value',0)
        rlist.append(cv>v if op=='gt' else cv>=v if op=='gte' else cv<v if op=='lt' else cv<=v)
    return {'triggered':all(rlist) if logic=='AND' else any(rlist),'sub_results':rlist}

@RuleEvaluator.register('absence')
def _eval_absence(self, s):
    mins = self.condition.get('absent_minutes',5)
    _,obj = self._latest(s)
    if not obj: return {'triggered':True}
    elapsed = (timezone.now()-obj.created_at).total_seconds()/60
    return {'triggered':elapsed>mins,'last_report_minutes_ago':round(elapsed,1)}

@RuleEvaluator.register('anomaly')
def _eval_anomaly(self, s):
    from monitoring.anomaly_detector import AnomalyDetector
    det = AnomalyDetector(method=self.condition.get('method','auto'))
    vals = self._series(s,30)
    if len(vals)<5: return {'triggered':False}
    ia,score,reason = det.detect(vals)
    return {'triggered':ia,'anomaly_score':round(score,4),'method_used':det.method_used,'reason':reason}
```

---

### Step 5: 异常检测算法库 — `monitoring/anomaly_detector.py`

```python
# monitoring/anomaly_detector.py
import statistics
from dataclasses import dataclass
from typing import List,Tuple

@dataclass
class AnomalyResult:
    is_anomaly: bool; score: float; method: str; reason: str; details: dict=None

class BaseDetector:
    method_name="base"
    def detect(self, series): raise NotImplementedError

class ZScoreDetector(BaseDetector):
    method_name="zscore"
    def __init__(self,threshold=3.0,window=30):
        self.threshold=threshold; self.window=window
    def detect(self,series):
        if len(series)<self.window: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        hist=series[-(self.window+1):-1]
        mu=statistics.mean(hist); sd=statistics.stdev(hist) if len(hist)>1 else 0
        if sd==0: return AnomalyResult(False,0,self.method_name,"zero_std")
        z=abs((series[-1]-mu)/sd); ok=z>self.threshold; sc=min(1.0,z/(self.threshold*2))
        return AnomalyResult(ok,sc,self.method_name,f"Z={z:.2f}(μ={mu:.2f},σ={sd:.2f})",
                              {'zscore':round(z,3),'mean':round(mu,3),'std':round(sd,3)})

class IQRDetector(BaseDetector):
    method_name="iqr"
    def __init__(self,k=1.5,window=30):
        self.k=k; self.window=window
    def detect(self,series):
        if len(series)<self.window: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        h=sorted(series[-(self.window+1):-1]); n=len(h)
        q1=h[n//4]; q3=h[3*n//4]; iqr=q3-q1
        if iqr==0: return AnomalyResult(False,0,self.method_name,"zero_iqr")
        lo=q1-self.k*iqr; hi=q3+self.k*iqr; latest=series[-1]
        if latest<lo:
            sc=min(1.0,(lo-latest)/iqr)
            return AnomalyResult(True,sc,self.method_name,f"<IQR下界{lo:.2f}",{'direction':'low'})
        if latest>hi:
            sc=min(1.0,(latest-hi)/iqr)
            return AnomalyResult(True,sc,self.method_name,f">IQR上界{hi:.2f}",{'direction':'high'})
        return AnomalyResult(False,0,self.method_name,"normal")

class MovingAvgDetector(BaseDetector):
    method_name="moving_avg"
    def __init__(self,mw=10,tf=2.0):
        self.mw=mw; self.tf=tf
    def detect(self,series):
        if len(series)<self.mw+1: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        mav=[]
        for i in range(self.mw,len(series)):
            mav.append(statistics.mean(series[i-self.mw:i]))
        actual=series[-1]; ma=mav[-1]
        res=[series[self.mw+i]-mav[i] for i in range(len(mav))]
        rsd=statistics.stdev(res) if len(res)>1 else 0
        dev=abs(actual-ma); th=self.tf*rsd if rsd>0 else ma*0.1
        dir_='high' if actual>ma else 'low'
        return AnomalyResult(dev>th,min(1.0,dev/(th*2))if th>0 else 0,self.method_name,
            f"偏差={dev:.2f}",{'ma':round(ma,3),'dev':round(dev,3),'direction':dir_})

class RateOfChangeDetector(BaseDetector):
    method_name="rate_of_change"
    def __init__(self,max_pct=50.0):
        self.max_pct=max_pct
    def detect(self,series):
        if len(series)<2: return AnomalyResult(False,0,self.method_name,"insufficient_data")
        prev=series[-2]; curr=series[-1]
        if prev==0: return AnomalyResult(False,0,self.method_name,"zero_base")
        pct=abs((curr-prev)/prev*100); ok=pct>self.max_pct
        sc=min(1.0,pct/(self.max_pct*2)); d='spike_up' if curr>prev else 'drop_down'
        return AnomalyResult(ok,sc,self.method_name,f"变化率={pct:.1f}%",{'pct':round(pct,2),'direction':d})

class CompositeAnomalyDetector(BaseDetector):
    method_name="composite"
    def __init__(self,detectors=None,vote_thr=0.5):
        self.detectors=detectors or [
            ZScoreDetector(threshold=2.5), IQRDetector(k=1.5),
            MovingAvgDetector(), RateOfChangeDetector()]
        self.vote_thr=vote_thr
    def detect(self,series):
        results=[]
        for d in self.detectors:
            try: results.append(d.detect(series))
            except: results.append(AnomalyResult(False,0,d.method_name,"error"))
        ac=sum(1 for r in results if r.is_anomaly); tot=len(results)
        vr=ac/tot if tot>0 else 0
        drs=[{"method":r.method,"anomaly":r.is_anomaly,"score":round(r.score,3)} for r in results]
        return AnomalyResult(vr>=self.vote_thr,round(vr,4),self.method_name,
            f"{ac}/{tot}算法判定异常",{'vote_ratio':round(vr,3),'results':drs})

class AnomalyDetector:
    def __init__(self,method='auto'):
        self.method=method; self.method_used=None
    def detect(self,values):
        if len(values)<5: return False,0.0,"数据不足"
        m={'zscore':ZScoreDetector(),'iqr':IQRDetector(),
           'moving_avg':MovingAvgDetector(),'rate_of_change':RateOfChangeDetector(),
           'composite':CompositeAnomalyDetector()}
        det=m.get(self.method)
        if not det:
            if len(values)<20: det=ZScoreDetector(threshold=2.5)
            else: det=CompositeAnomalyDetector(vote_thr=0.6)
        self.method_used=det.method_name
        r=det.detect(values)
        return r.is_anomaly,r.score,r.reason
```

---

### Step 6: 多渠道通知中心 — `monitoring/notification/channel_manager.py`

#### 6.1 创建 `monitoring/notification/__init__.py` (空文件)

#### 6.2 创建 `monitoring/notification/channel_manager.py`

```python
# monitoring/notification/channel_manager.py
import json,hmac,hashlib,base64,time,logging,urllib.parse
from datetime import datetime
from typing import List,Dict
from dataclasses import dataclass,field

logger=logging.getLogger(__name__)

@dataclass
class NotificationMessage:
    title:str; content:str; severity:str="P1"; alert_id:int=0
    server_name:str=""; metric_name:str=""
    current_value:float=0.0; threshold:float=0.0
    timestamp:str=field(default_factory=lambda:datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dingtalk_markdown(self):
        return {"msgtype":"markdown","markdown":{
            "title":self.title,"text":
            f"### {self.severity} {self.title}\n\n"
            f"- **服务器**: {self.server_name}\n- **指标**: {self.metric_name}\n"
            f"- **当前值**: {self.current_value}\n- **阈值**: {self.threshold}\n\n"
            f"{self.content}\n\n> {self.timestamp}"}}

    def to_wechat_text(self):
        return f'<font color="warning">{self.title}</font>\n{self.content}\n时间: {self.timestamp}'

    def to_email_html(self):
        c={'P0':'#ff4d4f','P1':'#fa8c16','P2':'#faad14','P3':'#52c41a'}
        color=c.get(self.severity,'#1890ff')
        return f'''<html><body style="font-family:sans-serif;padding:20px">
<div style="max-width:600px;margin:auto;border:1px solid #e8e8e8;border-radius:8px;overflow:hidden">
<div style="background:{color};color:white;padding:16px 24px"><h2 style="margin:0">{self.title}</h2>
<p style="margin:4px 0 0;opacity:.9">级别: {self.severity}</p></div>
<div style="padding:24px"><table style="width:100%;border-collapse:collapse">
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>服务器</b></td><td>{self.server_name}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>指标</b></td><td>{self.metric_name}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>当前值</b></td>
<td style="color:{color};font-weight:bold">{self.current_value}</td></tr>
<tr><td style="padding:8px;border-bottom:1px solid #eee"><b>阈值</b></td><td>{self.threshold}</td></tr>
<tr><td style="padding:8px"><b>触发时间</b></td><td>{self.timestamp}</td></tr></table>
<hr style="border:none;border-top:1px solid #eee;margin:16px 0">
<p style="color:#666;line-height:1.6">{self.content}</p></div>
<div style="background:#fafafa;padding:12px 24px;font-size:12px;color:#999;text-align:center">
AiOps 自动发送</div></div></body></html>'''

    def to_slack_attachment(self):
        e={'P0':'danger','P1':'warning','P2':'warning','P3':'good'}
        em={'P0':':rotating_light:','P1':':warning:','P2':':information_source:','P3':':bell:'}
        return {"attachments":[{"color":e.get(self.severity,'#439FE5'),
            "title":f"{em.get(self.severity,'')} {self.title}",
            "fields":[{"title":"服务器","value":self.server_name,"short":True},
                      {"title":"指标","value":self.metric_name,"short":True},
                      {"title":"当前值","value":str(self.current_value),"short":True},
                      {"title":"阈值","value":str(self.threshold),"short":True}],
            "text":self.content,"footer":"AiOps","ts":int(time.time())}]}


class DingTalkChannel:
    name="dingtalk"
    def __init__(self,cfg):
        self.url=cfg.get('webhook_url',''); self.secret=cfg.get('secret','')
        self.msg_type=cfg.get('msg_type','markdown')
    def send(self,msg):
        import requests
        try:
            payload=msg.to_dingtalk_markdown() if self.msg_type=='markdown' else {"msgtype":"text",
                "text":{"content":f"**{msg.title}**\n{msg.content}\n> {msg.timestamp}"}}
            url=self.url
            if self.secret:
                ts=str(round(time.time()*1000)); sig_str=f'{ts}\n{self.secret}'
                hc=hmac.new(self.secret.encode(),sig_str.encode(),digestmod=hashlib.sha256).digest()
                sign=urllib.parse.quote_plus(base64.b64encode(hc))
                url=f"{url}&timestamp={ts}&sign={sign}"
            r=requests.post(url,json=payload,timeout=10)
            ok=r.status_code==200 and r.json().get('errcode')==0
            return {'success':ok,'channel':self.name,'response':r.json() if ok else r.text}
        except Exception as e:
            logger.error(f"[DingTalk] {e}"); return {'success':False,'channel':self.name,'error':str(e)}

class WeChatChannel:
    name="wechat"
    def __init__(self,cfg): self.url=cfg.get('webhook_url','')
    def send(self,msg):
        import requests
        try:
            r=requests.post(self.url,json={"msgtype":"markdown",
                "markdown":{"content":msg.to_wechat_text()}},timeout=10)
            return {'success':r.status_code==200 and r.json().get('errcode')==0,'channel':self.name}
        except Exception as e:
            logger.error(f"[WeChat] {e}"); return {'success':False,'channel':self.name,'error':str(e)}

class EmailChannel:
    name="email"
    def __init__(self,cfg):
        self.host=cfg.get('smtp_host',''); self.port=cfg.get('smtp_port',587)
        self.user=cfg.get('smtp_user',''); self.pwd=cfg.get('smtp_pass','')
        self.frm=cfg.get('from_addr',''); self.tls=cfg.get('use_tls',True)
        self.to_addr=cfg.get('to_addrs','')
    def send(self,msg):
        import smtplib
        from email.mime.text import MIMEText; from email.mime.multipart import MIMEMultipart
        try:
            msg=MIMEMultipart('alternative')
            msg['Subject']=f"[{msg.severity}] {msg.title}"
            msg['From']=self.frm; msg['To']=self.to_addr
            msg.attach(MIMEText(msg.to_email_html(),'html','utf-8'))
            srv=smtplib.SMTP(self.host,self.port)
            if self.tls: srv.starttls()
            srv.login(self.user,self.pwd)
            srv.sendmail(self.frm,self.to_addr.split(','),msg.as_string()); srv.quit()
            return {'success':True,'channel':self.name}
        except Exception as e:
            logger.error(f"[Email] {e}"); return {'success':False,'channel':self.name,'error':str(e)}

class WebhookChannel:
    name="webhook"
    def __init__(self,cfg):
        self.url=cfg.get('url',''); self.method=cfg.get('method','POST')
        self.headers=cfg.get('headers',{})
    def send(self,msg):
        import requests
        try:
            r=requests.request(self.method,self.url,json={
                "alert_id":msg.alert_id,"title":msg.title,"content":msg.content,
                "severity":msg.severity,"server":msg.server_name,"metric":msg.metric_name,
                "current_value":msg.current_value,"threshold":msg.threshold,"timestamp":msg.timestamp},
                headers=self.headers,timeout=10)
            return {'success':r.status_code<400,'channel':self.name,'status_code':r.status_code}
        except Exception as e:
            return {'success':False,'channel':self.name,'error':str(e)}

CHANNEL_CLS={'dingtalk':DingTalkChannel,'wechat':WeChatChannel,
             'email':EmailChannel,'slack':None,'webhook':WebhookChannel}


class NotificationRouter:
    def __init__(self):
        self.channels={}
        self._load()

    def _load(self):
        from system.models import SystemConfig
        for name,cls in CHANNEL_CLS.items():
            if not cls: continue
            raw=SystemConfig.objects.filter(key=f'notify_{name}_config').first()
            if raw and raw.value:
                try:
                    cfg=json.loads(raw.value); self.channels[name]=cls(cfg)
                except Exception as e:
                    logger.error(f"[Notify] 加载{name}失败: {e}")

    def route_and_send(self,msg,target_channels):
        results=[]
        for ch in target_channels:
            c=self.channels.get(ch)
            if not c:
                results.append({'success':False,'channel':ch,'error':'not_configured'}); continue
            r=c.send(msg); results.append(r)
            st="OK" if r['success'] else f"FAIL({r.get('error','?')})"
            logger.info(f"[Notify] {ch}: {st}")
        return results


from celery import shared_task

@shared_task(bind=True,max_retries=3,default_retry_delay=60)
def send_alert_notifications(self,event_id):
    from monitoring.models import AlertEvent,NotificationLog
    try:
        event=AlertEvent.objects.select_related('rule','server').get(id=event_id)
        msg=NotificationMessage(
            title=f"【{event.rule.name}】{event.message}",content=event.detail or "",
            severity=event.severity,alert_id=event.id,
            server_name=event.server.hostname if event.server else "",
            metric_name=event.metric_name,current_value=event.current_value,
            threshold=event.threshold_value or 0)
        channels=event.rule.notify_channels or ['dingtalk']
        router=NotificationRouter(); results=router.route_and_send(msg,channels)
        event.notification_log=results; event.save(update_fields=['notification_log'])
        for r in results:
            NotificationLog.objects.create(alert_event=event,channel=r['channel'],
                status='sent' if r['success'] else 'failed',
                error_message=r.get('error',''),content_summary=msg.title[:200])
        af=all(not rr['success'] for rr in results)
        if af and self.request.retries<self.max_retries:
            raise self.retry(countdown=60*(self.request.retries+1))
        return results
    except AlertEvent.DoesNotExist:
        return {'error':'not_found'}
    except Exception as e:
        logger.error(f"[AlertNotify] {event_id}: {e}")
        raise self.retry(exc=e)
```

---

### Step 7: REST API 层 — `monitoring/api/views.py` + `monitoring/api/urls.py`

#### 7.1 创建 `monitoring/api/__init__.py` (空文件)

#### 7.2 创建 `monitoring/api/views.py`

```python
# monitoring/api/views.py
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import Count,Q
from datetime import timedelta

from monitoring.models import AlertRule, AlertEvent, AlertSilenceRule
from monitoring.engine.rule_evaluator import RuleEvaluator


@login_required
@require_GET
def api_rules(request):
    rules = AlertRule.objects.all().order_by('-created_at')
    data = [{
        'id': r.id,'name':r.name,'description':r.description or '',
        'rule_type':r.rule_type,'severity':r.severity,'status':r.status,
        'metric_name':r.metric_name,'condition_config':r.condition_config,
        'evaluate_interval':r.evaluate_interval,'cooldown_seconds':r.cooldown_seconds,
        'notify_channels':r.notify_channels,'trigger_count':r.trigger_count,
        'last_triggered_at':r.last_triggered_at.isoformat() if r.last_triggered_at else None,
        'created_at':r.created_at.isoformat(),
    } for r in rules]
    return JsonResponse({'code':0,'data':{'items':data,'total':len(data)}})


@login_required
@csrf_exempt
@require_POST
def api_rule_create(request):
    try:
        data = json.loads(request.body)
        rule = AlertRule.objects.create(
            name=data['name'], description=data.get('description',''),
            rule_type=data.get('rule_type','threshold'),
            severity=data.get('severity','P1'),
            metric_name=data.get('metric_name','cpu_usage'),
            condition_config=data.get('condition_config',{}),
            cooldown_seconds=data.get('cooldown_seconds',300),
            max_alerts_per_hour=data.get('max_alerts_per_hour',10),
            notify_channels=data.get('notify_channels',['dingtalk']),
            created_by=request.user,
        )
        return JsonResponse({'code':0,'data':{'id':rule.id}})
    except Exception as e:
        return JsonResponse({'code':1,'msg':str(e)})


@login_required
@csrf_exempt
@require_POST
def api_rule_toggle(request, pk):
    try:
        rule = AlertRule.objects.get(id=pk)
        rule.status = 'disabled' if rule.status == 'enabled' else 'enabled'
        rule.save()
        return JsonResponse({'code':0,'data':{'new_status':rule.status}})
    except AlertRule.DoesNotExist:
        return JsonResponse({'code':1,'msg':'规则不存在'}, status=404)


@login_required
@require_GET
def api_alerts(request):
    status_filter = request.GET.get('status','')
    severity = request.GET.get('severity','')
    page = int(request.GET.get('page',1))
    size = int(request.GET.get('size',20))

    qs = AlertEvent.objects.all()
    if status_filter: qs = qs.filter(status=status_filter)
    if severity: qs = qs.filter(severity=severity)

    total = qs.count()
    items = qs.order_by('-fired_at')[(page-1)*size:page*size]
    data = [{
        'id':a.id,'rule_name':a.rule.name,'server_name':a.server.hostname if a.server else '',
        'severity':a.severity,'status':a.status,'metric_name':a.metric_name,
        'current_value':a.current_value,'threshold_value':a.threshold_value,
        'message':a.message,'fired_at':a.fired_at.isoformat(),
        'duration_sec':int(a.duration),
    } for a in items]
    return JsonResponse({'code':0,'data':{'items':data,'total':total,'page':page}})


@login_required
@csrf_exempt
@require_POST
def api_alert_acknowledge(request, pk):
    try:
        event = AlertEvent.objects.get(id=pk)
        event.status = 'acknowledged'
        event.acknowledged_at = timezone.now()
        event.acknowledged_by = request.user
        event.save()
        return JsonResponse({'code':0})
    except AlertEvent.DoesNotExist:
        return JsonResponse({'code':1,'msg':'不存在'}, status=404)


@login_required
@csrf_exempt
@require_POST
def api_alert_resolve(request, pk):
    try:
        event = AlertEvent.objects.get(id=pk)
        event.status = 'resolved'
        event.resolved_at = timezone.now()
        event.save()
        return JsonResponse({'code':0})
    except AlertEvent.DoesNotExist:
        return JsonResponse({'code':1,'msg':'不存在'}, status=404)


@login_required
@csrf_exempt
@require_POST
def api_alert_silence(request):
    try:
        data = json.loads(request.body)
        silence = AlertSilenceRule.objects.create(
            name=data.get('name','临时静默'),
            match_severity=data.get('severity',''),
            start_time=timezone.now(),
            end_time=timezone.now()+timedelta(minutes=int(data.get('duration_minutes',60))),
            comment=data.get('comment',''),
            created_by=request.user,
        )
        return JsonResponse({'code':0,'data':{'id':silence.id}})
    except Exception as e:
        return JsonResponse({'code':1,'msg':str(e)})


@login_required
@require_GET
def api_alert_stats(request):
    now = timezone.now()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    stats = {
        'firing_count': AlertEvent.objects.filter(status='firing').count(),
        'today_total': AlertEvent.objects.filter(fired_at__gte=day_ago).count(),
        'week_total': AlertEvent.objects.filter(fired_at__gte=week_ago).count(),
        'hour_fired': AlertEvent.objects.filter(fired_at__gte=hour_ago).count(),
        'by_severity': dict(
            AlertEvent.objects.filter(status='firing')
            .values_list('severity').annotate(cnt=Count('id')).values_list('severity','cnt')
        ),
        'by_metric': dict(
            AlertEvent.objects.filter(status='firing',fired_at__gte=day_ago)
            .values_list('metric_name').annotate(cnt=Count('id')).values_list('metric_name','cnt')
        ),
        'active_rules': AlertRule.objects.filter(status='enabled').count(),
        'total_rules': AlertRule.objects.count(),
    }
    return JsonResponse({'code':0,'data':stats})


@login_required
@csrf_exempt
@require_POST
def api_rule_test(request):
    """Dry Run: 测试规则但不真正触发告警"""
    try:
        data = json.loads(request.body)
        rule_id = data.get('rule_id')
        evaluator = RuleEvaluator(AlertRule.objects.get(id=rule_id))
        fired, detail = evaluator.evaluate()
        return JsonResponse({'code':0,'data':{'would_fire':fired,'detail':detail}})
    except Exception as e:
        return JsonResponse({'code':1,'msg':str(e)})
```

#### 7.3 创建 `monitoring/api/urls.py`

```python
# monitoring/api/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('rules/', views.api_rules, name='api_rules'),
    path('rules/create/', views.api_rule_create, name='api_rule_create'),
    path('rules/<int:pk>/toggle/', views.api_rule_toggle, name='api_rule_toggle'),
    path('rules/test/', views.api_rule_test, name='api_rule_test'),
    path('alerts/', views.api_alerts, name='api_alerts'),
    path('alerts/stats/', views.api_alert_stats, name='api_alert_stats'),
    path('alerts/<int:pk>/ack/', views.api_alert_acknowledge, name='api_alert_ack'),
    path('alerts/<int:pk>/resolve/', views.api_alert_resolve, name='api_alert_resolve'),
    path('alerts/silence/', views.api_alert_silence, name='api_alert_silence'),
]
```

---

### Step 8: Celery 定时任务 — `monitoring/management/commands/evaluate_rules.py`

```python
# monitoring/management/commands/evaluate_rules.py
"""
管理命令: 启动规则评估调度器
用法: python manage.py evaluate_rules
"""

import logging
from apscheduler.schedulers.blocking import BlockingScheduler
from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from monitoring.engine.rule_evaluator import RuleEvaluator

logger = logging.getLogger(__name__)


def job_evaluate_all():
    """定时执行所有启用规则的评估"""
    logger.info("--- [RuleEngine] 开始周期性评估 ---")
    result = RuleEvaluator.evaluate_all()

    logger.info(
        f"[RuleEngine] 评估完成: 评估{result['evaluated']}条规则, "
        f"触发{result['fired']}次告警"
    )
    if result['errors']:
        for err in result['errors']:
            logger.error(f"[RuleEngine] 错误: {err}")


class Command(BaseCommand):
    help = '启动预警规则评估调度器 (基于APScheduler)'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('[RuleEngine] 预警规则评估器启动...'))

        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)

        # 默认每60秒评估一次所有启用的规则
        scheduler.add_job(job_evaluate_all, 'interval', seconds=60,
                         id='evaluate_alert_rules', replace_existing=True, max_instances=1)

        try:
            job_evaluate_all()  # 启动时立即执行一次
            scheduler.start()
        except KeyboardInterrupt:
            self.stdout.write("[RuleEngine] 已停止.")
```

---

### Step 9: 注册应用到 Django 配置

#### 9.1 修改 `ops_platform/settings.py`

在 `INSTALLED_APPS` 列表中添加 `'monitoring'`:

找到这一行:
```python
    'k8s_manager',  # K8s 多集群管理
]
```

改为:
```python
    'k8s_manager',  # K8s 多集群管理
    'monitoring',  # 智能监控告警 (Phase 1 新增)
]
```

在 LOGGING 的 loggers 字典末尾添加 monitoring 日志配置:

找到 `'k8s_manager': {...}` 之后，添加:

```python
        'monitoring': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
```

在 `CELERY_BEAT_SCHEDULE` 中添加规则评估任务 (可选，如果用 APScheduler 则不需要):

```python
    'evaluate-alert-rules-every-minute': {
        'task': 'monitoring.management.commands.evaluate_rules.job_evaluate_all',
        'schedule': crontab(minute='*/1'),
    },
```

#### 9.2 修改 `ops_platform/urls.py`

在文件末尾 `path('k8s/', ...)` 之后添加:

```python
    # === 监控告警 API (Phase 1 新增) ===
    path('api/monitoring/', include('monitoring.api.urls')),
```

同时在文件顶部添加 include 导入 (应该已经有了):

```python
from django.urls import path, include
```

---

### Step 10: Dashboard 增强 — 嵌入告警面板

在 [templates/index.html](file:///d:/codes/aiops/templates/index.html) 中，找到合适的位置（通常在主图表区域之后），追加以下 HTML 片段:

```html
<!-- ==================== 告警面板 (Phase 1 新增) ==================== -->
{% load humanize %}
<div class="row mt-4">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h5 class="mb-0">
                    <i class="fas fa-bell text-danger"></i> 活跃告警
                    <span id="alert-count" class="badge badge-danger ml-2">0</span>
                </h5>
                <div>
                    <button class="btn btn-sm btn-outline-primary" onclick="refreshAlerts()">
                        <i class="fas fa-sync-alt"></i> 刷新
                    </button>
                    <a href="/admin/monitoring/alertevent/" class="btn btn-sm btn-outline-secondary ml-1" target="_blank">
                        管理全部
                    </a>
                </div>
            </div>
            <div class="card-body p-0">
                <div id="alert-list-container">
                    <div class="text-center text-muted py-4" id="alert-loading">加载中...</div>
                    <table class="table table-hover mb-0" id="alert-table" style="display:none;">
                        <thead class="thead-light">
                            <tr>
                                <th width="60">级别</th>
                                <th>规则</th>
                                <th>服务器</th>
                                <th>消息</th>
                                <th width="80">状态</th>
                                <th width="120">触发时间</th>
                                <th width="140">操作</th>
                            </tr>
                        </thead>
                        <tbody id="alert-tbody"></tbody>
                    </table>
                    <div id="alert-empty" class="text-center text-muted py-4" style="display:none;">
                        <i class="fas fa-check-circle text-success fa-2x"></i>
                        <p class="mt-2 mb-0">暂无活跃告警</p>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- 快捷操作: 预置常用规则 -->
<div class="row mt-3">
    <div class="col-md-12">
        <div class="card">
            <div class="card-header">
                <h5 class="mb-0"><i class="fas fa-cog"></i> 快捷预置规则</h5>
            </div>
            <div class="card-body">
                <div class="d-flex flex-wrap gap-2">
                    <button class="btn btn-sm btn-outline-danger" onclick="createPresetRule('cpu_high')">
                        CPU > 90% 告警
                    </button>
                    <button class="btn btn-sm btn-outline-warning" onclick="createPresetRule('mem_high')">
                        内存 > 85% 告警
                    </button>
                    <button class="btn btn-sm btn-outline-info" onclick="createPresetRule('disk_high')">
                        磁盘 > 90% 告警
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" onclick="createPresetRule('agent_lost')">
                        Agent 掉线检测
                    </button>
                    <a href="/admin/monitoring/alertrule/add/" class="btn btn-sm btn-primary" target="_blank">
                        <i class="fas fa-plus"></i> 自定义规则
                    </a>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
// ========== 告警面板 JS ==========
const ALERT_API = '/api/monitoring/alerts/';

function refreshAlerts() {
    fetch(ALERT_API + '?status=firing&size=20')
        .then(r => r.json())
        .then(resp => {
            const items = resp.data.items || [];
            document.getElementById('alert-count').textContent = items.length;
            
            const tbody = document.getElementById('alert-tbody');
            const table = document.getElementById('alert-table');
            const empty = document.getElementById('alert-empty');
            const loading = document.getElementById('alert-loading');

            loading.style.display = 'none';
            
            if (items.length === 0) {
                table.style.display = 'none';
                empty.style.display = 'block';
                tbody.innerHTML = '';
                return;
            }

            empty.style.display = 'none';
            table.style.display = 'table';

            const sevColors = {'P0':'danger','P1':'warning','P2':'info','P3':'secondary'};
            const statColors = {'firing':'danger','acknowledged':'warning','resolved':'success'};
            const statLabels = {'firing':'触发中','acknowledged':'已确认','resolved':'已恢复'};

            tbody.innerHTML = items.map(a => `
                <tr>
                    <td><span class="badge badge-${sevColors[a.severity]||'secondary'}">${a.severity}</span></td>
                    <td>${esc(a.rule_name)}</td>
                    <td>${esc(a.server_name)||'-'}</td>
                    <td title="${esc(a.message)}">${esc(a.message).substring(0,60)}${a.message.length>60?'...':''}</td>
                    <td><span class="badge badge-${statColors[a.status]||'secondary'}">${statLabels[a.status]}</span></td>
                    <td>${timeAgo(a.fired_at)}</td>
                    <td>
                        ${a.status==='firing'?`
                            <button class="btn btn-xs btn-outline-success" onclick="ackAlert(${a.id})">确认</button>
                            <button class="btn btn-xs btn-outline-secondary" onclick="resolveAlert(${a.id})">恢复</button>
                        `:''}
                    </td>
                </tr>
            `).join('');
        })
        .catch(err => console.error('加载告警失败:', err));
}

function ackAlert(id) {
    fetch(`/api/monitoring/alerts/${id}/ack/`, {method:'POST'})
        .then(() => refreshAlerts());
}

function resolveAlert(id) {
    fetch(`/api/monitoring/alerts/${id}/resolve/`, {method:'POST'})
        .then(() => refreshAlerts());
}

function createPresetRule(type) {
    const presets = {
        cpu_high: {name:'CPU使用率过高',metric_name:'cpu_usage',rule_type:'threshold',
                  condition_config:{operator:'gt',value:90},severity:'P1'},
        mem_high: {name:'内存使用率过高',metric_name:'mem_usage',rule_type:'threshold',
                  condition_config:{operator:'gt',value:85},severity:'P1'},
        disk_high: {name:'磁盘空间不足',metric_name:'disk_usage',rule_type:'threshold',
                   condition_config:{operator:'gt',value:90},severity:'P2'},
        agent_lost: {name:'Agent掉线检测',metric_name:'cpu_usage',rule_type:'absence',
                   condition_config:{absent_minutes:5},severity:'P1'}
    };
    const p = presets[type];
    if (!p) return;
    
    // 通过API创建规则
    fetch('/api/monitoring/rules/create/', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify(p)
    }).then(r=>r.json()).then(resp=>{
        if(resp.code===0){
            alert(`规则 "${p.name}" 创建成功! ID=${resp.data.id}`);
            refreshAlerts();
        } else {
            alert('创建失败: '+resp.msg);
        }
    });
}

function esc(s){ const d=document.createElement('div'); d.textContent=s; return d.innerHTML;}
function timeAgo(isoStr){
    const diff=(Date.now()-new Date(isoStr).getTime())/1000;
    if(diff<60)return Math.floor(diff)+'秒前';
    if(diff<3600)return Math.floor(diff/60)+'分钟前';
    if(diff<86400)return Math.floor(diff/3600)+'小时前';
    return Math.floor(diff/86400)+'天前';
}

// 页面加载完成后自动刷新告警
document.addEventListener('DOMContentLoaded', function(){
    refreshAlerts();
    // 每30秒自动刷新一次
    setInterval(refreshAlerts, 30000);
});
</script>
<!-- ==================== 告警面板结束 ==================== -->
```

---

## ✅ 执行验证清单

完成以上所有步骤后，按顺序执行以下验证命令：

### V1. 数据库迁移

```bash
cd d:\codes\aiops
python manage.py makemigrations monitoring
python manage.py migrate
```

预期输出应包含 `AlertRule`, `AlertEvent`, `AlertSilenceRule`, `NotificationLog` 四张新表。

### V2. 验证 Admin 后台

启动服务后访问 `http://127.0.0.1:8000/admin/`，应能看到新增的：
- **预警规则** (AlertRule)
- **告警事件** (AlertEvent)
- **静默规则** (AlertSilenceRule)
- **通知记录** (NotificationLog)

### V3. 预置一条测试规则

通过 Admin 或 API 创建规则:
```json
POST /api/monitoring/rules/create/
{
    "name": "CPU高负载告警",
    "rule_type": "threshold",
    "severity": "P1",
    "metric_name": "cpu_usage",
    "condition_config": {"operator": "gt", "value": 90},
    "notify_channels": ["dingtalk"],
    "cooldown_seconds": 300
}
```

### V4. 手动触发规则评估

```bash
python manage.py shell
>>> from monitoring.engine.rule_evaluator import RuleEvaluator
>>> RuleEvaluator.evaluate_all()
```

或直接运行 Celery 任务:
```bash
celery -A ops_platform worker -l info -B
# 另开终端:
python manage.py evaluate_rules
```

### V5. 验证 Dashboard 告警面板

访问首页 `http://127.0.0.1:8000/`，页面底部应出现:
- **活跃告警** 表格 (带自动刷新)
- **快捷预置规则** 按钮 (一键创建常用规则)

### V6. 验证 API 端点

```bash
curl http://127.0.0.1:8000/api/monitoring/alerts/stats/
# 应返回 JSON 统计数据
```

---

## 🔗 文件依赖关系图 (执行顺序)

```
Step 1: 目录结构 + __init__.py 文件 (无依赖)
  ↓
Step 2: models.py (无依赖)
  ↓
Step 3: admin.py (依赖 Step 2 的 models)
  ↓
Step 4: engine/rule_evaluator.py (依赖 Step 2 的 models)
  ↓
Step 5: anomaly_detector.py (无外部依赖)
  ↓
Step 6: notification/channel_manager.py (依赖 Step 2 的 models)
  ↓
Step 7: api/views.py + urls.py (依赖 Step 2,4,6)
  ↓
Step 8: management/commands/evaluate_rules.py (依赖 Step 4)
  ↓
Step 9: settings.py + urls.py 修改 (注册所有以上组件)
  ↓
Step 10: index.html 增强 (依赖 Step 7 的 API)
  ↓
V1: makemigrations + migrate
V2-V6: 功能验证
```

---

## ⚠️ 注意事项

1. **cmdb/models.py 中需要确保 ServerGroup 有 ManyToMany 关系字段** 给 AlertRule 使用。如果当前 `Server` 模型没有 `groups` 反向关系，需要在 AlertRule 的 M2M 字段中使用 `related_name='alert_rules'` (已在模型中定义)。如遇 `Related name` 冲突请调整。

2. **SystemConfig 表需存在** 用于存储通知渠道配置。项目已有此表 ([system/models.py](file:///d:/codes/aiops/system/models.py))。

3. **Celery Worker 必须运行** 才能处理异步通知任务。确保 Redis 连接正常。

4. **首次运行建议先创建预置规则** 再启动采集器，这样采集到的数据会立即被规则评估。

---

> **文档结束** — 本计划涵盖从零到可运行的完整 Phase 1 开发流程，每段代码均可直接复制使用。
