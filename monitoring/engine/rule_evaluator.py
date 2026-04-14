import logging
import statistics
from datetime import timedelta
from asgiref.sync import async_to_sync
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
        if AlertEvent.objects.filter(rule=self.rule,server=server,status='firing',
            fired_at__gte=timezone.now()-timedelta(seconds=self.rule.cooldown_seconds)).exists():
            return
        now = timezone.now()
        if AlertSilenceRule.objects.filter(is_active=True,start_time__lte=now,end_time__gte=now
            ).filter(dj_models.Q(match_server=server)|dj_models.Q(match_server__isnull=True)
            ).filter(dj_models.Q(match_severity='')|dj_models.Q(match_severity=self.rule.severity)
            ).exists():
            return
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

        try:
            from monitoring.tasks import on_alert_fired
            on_alert_fired.delay(event.id)
        except Exception as e:
            logger.error(f"[RuleEngine] 升级调度失败: {e}")

        if result.get('triggered') and self.rule.rule_type == 'anomaly':
            from monitoring.ai_callback import anomaly_ai_callback_task
            try:
                anomaly_ai_callback_task.delay(
                    event_id=event.id,
                    server_id=server.id,
                    metric_name=self.rule.metric_name
                )
                logger.info(f"[RuleEngine] 已提交AI诊断任务: event={event.id}")
            except Exception as e:
                logger.error(f"[RuleEngine] 提交AI回调失败: {e}")

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
                    alert_event=event,
                    raw_values=self._series(server, 30),
                )
            except Exception as e:
                logger.error(f"[RuleEngine] 记录AnomalyHistory失败: {e}")

        if result.get('triggered'):
            try:
                from channels.layers import get_channel_layer
                import json
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)('monitoring', {
                    'type': 'monitoring_event',
                    'data': {
                        'event_type': 'alert_fired',
                        'alert_id': event.id,
                        'rule_name': event.rule.name,
                        'severity': event.severity,
                        'server_hostname': server.hostname if server else '',
                        'server_id': server.id if server else None,
                        'metric_name': event.metric_name,
                        'current_value': event.current_value,
                        'message': event.message,
                        'fired_at': event.fired_at.isoformat(),
                    }
                })
                logger.info(f"[RuleEngine] 告警已广播: event={event.id}")
            except Exception as e:
                logger.warning(f"[RuleEngine] 告警广播失败: {e}")

        if result.get('triggered'):
            try:
                from monitoring.aggregation.alert_aggregator import AlertAggregator
                is_storm = AlertAggregator.check_storm(server.id if server else None)
                if not is_storm:
                    group = AlertAggregator.aggregate(event)
                    logger.info(f"[RuleEngine] 告警已聚合: group={group.id} count={group.alert_count}")
            except Exception as e:
                logger.warning(f"[RuleEngine] 聚合失败: {e}")

            try:
                from monitoring.remediation.remediation_engine import RemediationEngine
                remediation_results = RemediationEngine.evaluate_and_execute(event)
                if remediation_results:
                    logger.info(f"[RuleEngine] 自愈评估: {[(r['action'], r['status']) for r in remediation_results]}")
            except Exception as e:
                logger.warning(f"[RuleEngine] 自愈评估失败: {e}")

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
