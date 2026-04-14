import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST, require_http_methods
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
    try:
        data = json.loads(request.body)
        rule_id = data.get('rule_id')
        evaluator = RuleEvaluator(AlertRule.objects.get(id=rule_id))
        fired, detail = evaluator.evaluate()
        return JsonResponse({'code':0,'data':{'would_fire':fired,'detail':detail}})
    except Exception as e:
        return JsonResponse({'code':1,'msg':str(e)})


@login_required
@require_GET
def api_anomaly_timeline(request):
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
    from monitoring.anomaly_marker import AnomalyMarkerService
    data = AnomalyMarkerService.get_anomaly_detail(anomaly_id)
    if not data:
        return JsonResponse({'code':1,'msg':'异常记录不存在'})
    return JsonResponse({'code':0,'data':data})


@login_required
@require_GET
def api_anomaly_markpoints(request):
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


@login_required
@require_GET
def api_topn(request):
    from cmdb.models import Server, ServerMetric
    from django.db.models import Subquery, OuterRef

    metric = request.GET.get('metric', 'cpu_usage')
    limit = int(request.GET.get('limit', 10))

    field_map = {
        'cpu_usage': 'cpu_usage', 'mem_usage': 'mem_usage',
        'disk_usage': 'disk_usage', 'load_1min': 'load_1min',
        'net_in': 'net_in', 'net_out': 'net_out',
    }
    db_field = field_map.get(metric)
    if not db_field:
        return JsonResponse({'code':1,'msg':'无效指标'})

    subq = ServerMetric.objects.filter(
        server=OuterRef('id')
    ).order_by('-collected_at').values(db_field)[:1]

    qs = Server.objects.filter(status='Running').annotate(
        latest_val=Subquery(subq)
    ).exclude(latest_val__isnull=True).order_by('-latest_val')[:limit]

    items = [{
        'rank': i+1,
        'server_id': s.id,
        'hostname': s.hostname,
        'ip_address': s.ip_address,
        'value': round(s.latest_val or 0, 2),
    } for i, s in enumerate(qs)]

    return JsonResponse({'code':0,'data':{'metric':metric,'items':items}})


@login_required
@require_GET
def api_trend_aggregated(request):
    from cmdb.models import ServerMetric
    from datetime import timedelta as td

    server_id = request.GET.get('server_id')
    metric = request.GET.get('metric', 'cpu_usage')
    range_str = request.GET.get('range', '24h')

    range_map = {'1h':1,'6h':6,'24h':24,'7d':168,'30d':720}
    hours = range_map.get(range_str, 24)

    since = timezone.now() - td(hours=hours)

    if hours <= 6:
        interval_minutes = 1
    elif hours <= 24:
        interval_minutes = 5
    elif hours <= 168:
        interval_minutes = 30
    else:
        interval_minutes = 120

    field_map = {
        'cpu_usage':'cpu_usage','mem_usage':'mem_usage',
        'disk_usage':'disk_usage','net_in':'net_in','net_out':'net_out',
    }
    attr = field_map.get(metric, 'cpu_usage')

    qs = ServerMetric.objects.filter(collected_at__gte=since).order_by('collected_at')
    if server_id:
        try:
            qs = qs.filter(server_id=int(server_id))
        except ValueError:
            pass

    all_metrics = list(qs.values_list('collected_at', attr))

    if not all_metrics:
        return JsonResponse({'code':0,'data':{'times':[],'values':[],'avg':0,'max':0,'min':0}})

    if len(all_metrics) > 200:
        step = max(1, len(all_metrics) // 200)
        sampled = [all_metrics[i] for i in range(0, len(all_metrics), step)]
    else:
        sampled = all_metrics

    values = [float(v[1]) for v in sampled if v[1] is not None]
    times = [v[0].strftime('%H:%M') if hours <= 24 else v[0].strftime('%m-%d %H:%M') for v in sampled]

    avg = sum(values) / len(values) if values else 0
    max_val = max(values) if values else 0
    min_val = min(values) if values else 0

    return JsonResponse({'code':0,'data':{
        'times':times,'values':[round(v,2) for v in values],
        'avg':round(avg,2),'max':round(max_val,2),'min':round(min_val,2),
    }})


@login_required
@require_GET
def api_export_report_pdf(request):
    from django.http import HttpResponse
    from datetime import timedelta as td

    server_id = request.GET.get('server_id')
    range_str = request.GET.get('range', '24h')

    range_map = {'1h':1,'6h':6,'24h':24,'7d':168,'30d':720}
    hours = range_map.get(range_str, 24)
    since = timezone.now() - td(hours=hours)

    from cmdb.models import Server, ServerMetric
    servers = list(Server.objects.filter(status='Running').values('id','hostname','ip_address','status'))
    if server_id:
        try:
            servers = [s for s in servers if s['id'] == int(server_id)]
        except ValueError:
            pass

    metrics_qs = ServerMetric.objects.filter(collected_at__gte=since).order_by('-collected_at')[:200]
    recent_metrics = list(metrics_qs.values(
        'server__hostname','cpu_usage','mem_usage','disk_usage',
        'load_1min','collected_at'
    ))

    alerts_qs = AlertEvent.objects.filter(fired_at__gte=since).select_related('rule','server').order_by('-fired_at')[:50]
    alerts_list = [{
        'rule': str(a.rule.name), 'severity': a.severity,
        'server': str(a.server.hostname) if a.server else '-',
        'metric': a.metric_name or '-',
        'value': str(a.current_value or '-'),
        'status': a.status,
        'fired': a.fired_at.strftime('%Y-%m-%d %H:%M:%S'),
    } for a in alerts_qs]

    anomaly_qs = AnomalyHistory.objects.filter(detected_at__gte=since).select_related('server').order_by('-detected_at')[:20]
    anomaly_list = [{
        'server': str(a.server.hostname) if a.server else '-',
        'metric': a.metric_name or '-', 'score': round(a.anomaly_score or 0, 3),
        'method': a.method_used or '-', 'detected': a.detected_at.strftime('%Y-%m-%d %H:%M'),
    } for a in anomaly_qs]

    html_content = f"""
    <!DOCTYPE html><html><head><meta charset="utf-8">
    <style>
      body {{ font-family: "Microsoft YaHei", sans-serif; font-size: 12px; margin: 40px; color: #333; }}
      h1 {{ color: #1890ff; font-size: 22px; border-bottom: 2px solid #1890ff; padding-bottom: 8px; }}
      h2 {{ color: #333; font-size: 16px; margin-top: 24px; border-left: 4px solid #1890ff; padding-left: 10px; }}
      table {{ width: 100%; border-collapse: collapse; margin: 8px 0; font-size: 11px; }}
      th {{ background: #f0f2f5; text-align: left; padding: 6px 10px; border: 1px solid #ddd; }}
      td {{ padding: 5px 10px; border: 1px solid #eee; }}
      tr:nth-child(even) {{ background: #fafafa; }}
      .summary {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0; }}
      .summary-item {{ background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 6px; padding: 12px 18px; min-width: 140px; }}
      .summary-item .val {{ font-size: 20px; font-weight: bold; color: #52c41a; }}
      .meta {{ color: #999; font-size: 11px; margin-top: 30px; border-top: 1px solid #eee; padding-top: 8px; }}
      .badge-danger {{ color:#fff;background:#ff4d4f;padding:1px 6px;border-radius:3px;font-size:10px; }}
      .badge-warning {{ color:#fff;background:#faad14;padding:1px 6px;border-radius:3px;font-size:10px; }}
    </style></head><body>
    <h1>📊 AIOps 运维监控报告</h1>
    <div class="meta">生成时间：{timezone.now().strftime('%Y-%m-%d %H:%M:%S')} | 时间范围：最近{range_str} | 服务器数：{len(servers)}</div>

    <div class="summary">
      <div class="summary-item"><div class="val">{len(servers)}</div><div>监控服务器</div></div>
      <div class="summary-item"><div class="val">{len(recent_metrics)}</div><div>指标采样点</div></div>
      <div class="summary-item"><div class="val">{len(alerts_list)}</div><div>告警事件</div></div>
      <div class="summary-item"><div class="val">{len(anomaly_list)}</div><div>异常记录</div></div>
    </div>

    <h2>🖥️ 服务器列表</h2>
    <table><tr><th>#</th><th>主机名</th><th>IP地址</th><th>状态</th></tr>
    {"".join([f'<tr><td>{i+1}</td><td>{s["hostname"]}</td><td>{s["ip_address"]}</td><td>{s["status"]}</td></tr>' for i,s in enumerate(servers)])}
    </table>

    <h2>📈 最新指标快照 (Top 20)</h2>
    <table><tr><th>主机名</th><th>CPU%</th><th>内存%</th><th>磁盘%</th><th>负载</th><th>时间</th></tr>
    {"".join([f'<tr><td>{m["server__hostname"]}</td><td>{m["cpu_usage"]}</td><td>{m["mem_usage"]}</td><td>{m["disk_usage"]}</td><td>{m["load_1min"]}</td><td>{m["collected_at"].strftime("%H:%M") if m["collected_at"] else "-"}</td></tr>' for m in recent_metrics[:20]])}
    </table>

    <h2>🚨 告警事件列表</h2>
    <table><tr><th>规则名称</th><th>级别</th><th>主机</th><th>指标</th><th>当前值</th><th>状态</th><th>触发时间</th></tr>
    {"".join([f'<tr><td>{a["rule"]}</td><td><span class="badge-{"danger" if a["severity"]=="P0" or a["severity"]=="P1" else "warning"}">{a["severity"]}</span></td><td>{a["server"]}</td><td>{a["metric"]}</td><td>{a["value"]}</td><td>{a["status"]}</td><td>{a["fired"]}</td></tr>' for a in alerts_list])}
    </table>

    <h2>⚠️ 异常检测记录</h2>
    <table><tr><th>主机</th><th>指标</th><th>异常分数</th><th>方法</th><th>检测时间</th></tr>
    {"".join([f'<tr><td>{a["server"]}</td><td>{a["metric"]}</td><td>{a["score"]}</td><td>{a["method"]}</td><td>{a["detected"]}</td></tr>' for a in anomaly_list])}
    </table>

    <div class="meta">
      本报告由 AIOps 监控平台自动生成 · Powered by Django + ECharts + Celery + WebSocket
    </div>
    </body></html>
    """

    try:
        from weasyprint import HTML
        pdf_file = HTML(string=html_content).write_pdf()
        response = HttpResponse(pdf_file, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="aiops-report-{timezone.now().strftime("%Y%m%d_%H%M%S")}.pdf"'
        return response
    except ImportError:
        return JsonResponse({'code':1,'msg':'PDF导出需要安装 weasyprint: pip install weasyprint'})
    except Exception as e:
        logger.error(f"[Export] PDF生成失败: {e}")
        return JsonResponse({'code':1,'msg':f'PDF生成失败: {str(e)}'})


# ==================== Phase 4: 智能运维增强 API ====================

@login_required
@require_GET
def api_correlation_groups(request):
    from monitoring.correlation.correlator import Correlator
    summary = Correlator.get_correlation_summary()
    return JsonResponse({'code':0,'data':{'clusters':summary,'total':len(summary)}})


@login_required
@require_GET
def api_dashboard_overview(request):
    from cmdb.models import Server
    from django.db.models import Count, Avg, Q
    from datetime import timedelta as td

    now = timezone.now()
    servers_total = Server.objects.count()
    servers_up = Server.objects.filter(status='Running').count()
    servers_down = servers_total - servers_up

    firing_count = AlertEvent.objects.filter(status='firing').count()
    resolved_today = AlertEvent.objects.filter(
        status='resolved', resolved_at__gte=now - td(hours=24)
    ).count()

    acked_events = AlertEvent.objects.exclude(acknowledged_at__isnull=True)
    mtta_val = 0.0
    if acked_events.exists():
        mtta_qs = acked_events.annotate(
            diff=ExtractSecond('acknowledged_at') - ExtractSecond('fired_at')
        )
        mtta_val = round(mtta_qs.aggregate(avg=Avg('diff'))['avg'] / 60, 1) or 0

    resolved_qs = AlertEvent.objects.exclude(resolved_at__isnull=True)
    mttr_val = 0.0
    if resolved_qs.exists():
        mttr_val = round(resolved_qs.aggregate(
            avg=Avg(ExtractSecond('resolved_at') - ExtractSecond('fired_at'))
        )['avg'] / 60, 1) or 0

    anomaly_today = AnomalyHistory.objects.filter(detected_at__gte=now - td(hours=24)).count()
    anomaly_high = AnomalyHistory.objects.filter(
        detected_at__gte=now - td(hours=24), severity='high'
    ).count()

    alerts_7d = []
    for i in range(7):
        day_start = now - td(days=i+1)
        day_end = now - td(days=i)
        c = AlertEvent.objects.filter(fired_at__gte=day_start, fired_at__lt=day_end).count()
        alerts_7d.append(c)
    alerts_7d.reverse()

    anomalies_7d = []
    for i in range(7):
        day_start = now - td(days=i+1)
        day_end = now - td(days=i)
        c = AnomalyHistory.objects.filter(detected_at__gte=day_start, detected_at__lt=day_end).count()
        anomalies_7d.append(c)
    anomalies_7d.reverse()

    sla_24h = round((1 - (servers_down / max(servers_total, 1))) * 100, 2) if servers_total else 100

    group_stats = AlertGroup.objects.filter(status='firing').aggregate(
        total=Count('id'), avg_count=Avg('alert_count')
    )

    return JsonResponse({'code':0,'data':{
        'servers': {'total': servers_total, 'up': servers_up, 'down': servers_down},
        'alerts': {
            'firing': firing_count,
            'resolved_today': resolved_today,
            'mtta_minutes': mtta_val,
            'mttr_minutes': mttr_val,
            'sla_24h': sla_24h,
            'active_groups': group_stats['total'] or 0,
            'avg_group_size': round(group_stats['avg_count'] or 0, 1),
        },
        'anomalies': {
            'today': anomaly_today,
            'high_severity': anomaly_high,
        },
        'trend': {
            'alerts_7d': alerts_7d,
            'anomalies_7d': anomalies_7d,
        },
    }})


from django.db.models.functions import ExtractSecond

@login_required
@require_GET
def api_runbook_search(request):
    from monitoring.runbook.recommender import RunbookRecommender

    q = request.GET.get('q', '')
    category = request.GET.get('category', '')
    entries = RunbookRecommender.search(query_text=q, category=category or None)
    data = [{
        'id': e.id, 'title': e.title, 'category': e.category,
        'solution_preview': e.solution[:200],
        'tags': e.tag_list, 'score': e.effectiveness_score,
        'usage': e.usage_count,
    } for e in entries]
    return JsonResponse({'code':0,'data':{'items':data,'total':len(data)}})


@login_required
@require_GET
def api_runbook_recommend(request):
    from monitoring.runbook.recommender import RunbookRecommender

    alert_id = request.GET.get('alert_id')
    limit = int(request.GET.get('limit', 5))
    results = []
    if alert_id:
        try:
            event = AlertEvent.objects.select_related('rule','server').get(id=int(alert_id))
            results = RunbookRecommender.recommend_for_alert(event, limit=limit)
        except (AlertEvent.DoesNotExist, ValueError):
            pass
    return JsonResponse({'code':0,'data':{'recommendations':results}})


@require_POST
@login_required
def api_runbook_feedback(request):
    from monitoring.runbook.recommender import RunbookRecommender
    import json
    try:
        body = json.loads(request.body)
        entry_id = body.get('entry_id')
        is_effective = body.get('is_effective', True)
        ok = RunbookRecommender.record_feedback(entry_id, bool(is_effective))
        return JsonResponse({'code':0 if ok else 1,'msg':'ok' if ok else 'not found'})
    except Exception as e:
        return JsonResponse({'code':1,'msg':str(e)})


@login_required
@require_GET
def api_remediation_history(request):
    qs = RemediationHistory.objects.select_related('action','alert_event__rule','alert_event__server').order_by('-started_at')
    alert_id = request.GET.get('alert_id')
    status_filter = request.GET.get('status')
    if alert_id:
        try: qs = qs.filter(alert_event_id=int(alert_id))
        except ValueError: pass
    if status_filter:
        qs = qs.filter(status=status_filter)

    items = [{
        'id': h.id, 'action_name': h.action.name, 'status': h.status,
        'alert_rule': h.alert_event.rule.name if h.alert_event.rule else '',
        'server': h.alert_event.server.hostname if h.alert_event.server else '',
        'started_at': h.started_at.isoformat(),
        'finished_at': h.finished_at.isoformat() if h.finished_at else None,
        'output_preview': (h.output or '')[:150],
    } for h in qs[:50]]
    return JsonResponse({'code':0,'data':{'items':items}})


@login_required
@require_POST
def api_remediation_execute(request):
    from monitoring.remediation.remediation_engine import RemediationEngine
    import json
    try:
        body = json.loads(request.body)
        alert_id = body.get('alert_id')
        event = AlertEvent.objects.get(id=int(alert_id))
        results = RemediationEngine.evaluate_and_execute(event)
        return JsonResponse({'code':0,'data':results})
    except AlertEvent.DoesNotExist:
        return JsonResponse({'code':1,'msg':'告警不存在'})
    except Exception as e:
        logger.error(f"[API] 执行修复失败: {e}")
        return JsonResponse({'code':1,'msg':str(e)})


# ==================== Phase 5: 数据管道与高级运维 API ====================

import secrets
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def api_agent_push(request):
    if request.method != 'POST':
        return JsonResponse({'code':1,'msg':'POST only'}, status=405)

    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    token_str = auth_header.replace('Bearer ', '') if auth_header.startswith('Bearer ') else ''

    if not token_str:
        return JsonResponse({'code':1,'msg':'missing_token'}, status=401)

    from monitoring.agent.push_api import AgentPushHandler
    agent = AgentPushHandler.authenticate(token_str)
    if not agent:
        return JsonResponse({'code':1,'msg':'invalid_token'}, status=403)

    try:
        import json
        payload = json.loads(request.body)
    except (json.JSONDecodeError, TypeError):
        return JsonResponse({'code':1,'msg':'invalid_json'}, status=400)

    result = AgentPushHandler.push_metrics(agent, payload)
    return JsonResponse({'code':0, 'data': result})


@login_required
@require_GET
def api_agent_tokens(request):
    tokens = list(AgentToken.objects.select_related('server').all())
    data = [{
        'id': t.id, 'name': t.name,
        'server_hostname': t.server.hostname if t.server else '',
        'is_active': t.is_active,
        'last_seen_at': t.last_seen_at.isoformat() if t.last_seen_at else None,
        'token_preview': (t.token or '')[:16] + '...',
    } for t in tokens]
    return JsonResponse({'code':0,'data':{'items':data}})


@login_required
@require_POST
def api_agent_create_token(request):
    import json
    try:
        body = json.loads(request.body)
        name = body.get('name', '')
        server_id = body.get('server_id')
    except:
        return JsonResponse({'code':1,'msg':'bad request'})

    from monitoring.agent.push_api import generate_token
    token_str = generate_token()
    server = None
    if server_id:
        try: server = CMDBServer.objects.get(id=int(server_id))
        except: pass

    at = AgentToken.objects.create(name=name, token=token_str, server=server)
    return JsonResponse({'code':0,'data':{'id':at.id,'token':token_str}})


@login_required
@require_GET
def api_topology_graph(request):
    from monitoring.topology.tracker import TopologyTracker
    graph = TopologyTracker.get_full_graph()
    return JsonResponse({'code':0,'data':graph})


@login_required
@require_GET
def api_topology_impact(request):
    node_id = request.GET.get('node_id')
    if not node_id:
        return JsonResponse({'code':1,'msg':'missing node_id'})
    from monitoring.topology.tracker import TopologyTracker
    impact = TopologyTracker.get_impact_analysis(int(node_id))
    if not impact:
        return JsonResponse({'code':1,'msg':'node not found'})
    return JsonResponse({'code':0,'data':impact})


@login_required
@require_GET
def api_topology_nodes(request):
    nodes = list(ServiceTopology.objects.select_related('server').prefetch_related('depends_on').all())
    data = [{
        'id': n.id, 'name': n.name, 'type': n.service_type,
        'server_id': n.server_id, 'server_name': n.server.hostname if n.server else '',
        'health_endpoint': n.health_endpoint or '',
        'depends_on': [d.id for d in n.depends_on.all()],
    } for n in nodes]
    return JsonResponse({'code':0,'data':{'items':data}})


@require_POST
@login_required
def api_topology_create_node(request):
    import json
    body = json.loads(request.body)
    node = ServiceTopology.objects.create(
        name=body.get('name',''),
        service_type=body.get('type','application'),
        health_endpoint=body.get('health_endpoint',''),
    )
    if body.get('server_id'):
        try: node.server_id = int(body['server_id'])
        except: pass
        node.save()
    dep_ids = body.get('depends_on', [])
    for did in dep_ids:
        try: node.depends_on.add(int(did))
        except: pass
    return JsonResponse({'code':0,'data':{'id':node.id}})


@login_required
@require_GET
def api_health_scores(request):
    from monitoring.health.scorer import HealthScorer
    days = int(request.GET.get('days', 7))
    server_id = request.GET.get('server_id')
    if server_id:
        history = HealthScorer.get_history(int(server_id), days)
        return JsonResponse({'code':0,'data':{'history':history}})
    ranking = HealthScorer.get_ranking(limit=30)
    return JsonResponse({'code':0,'data':{'ranking':ranking}})


@login_required
@require_POST
def api_health_scan_now(request):
    from monitoring.health.scorer import HealthScorer as HS
    results = HS.scan_all_servers()
    return JsonResponse({'code':0,'data':{'scanned':len(results),'results':results[:20]}})


@login_required
@require_GET
def api_dashboards_saved(request):
    mine = SavedDashboard.objects.filter(owner=request.user).order_by('-updated_at')
    public = SavedDashboard.objects.filter(is_public=True).exclude(owner=request.user) if request.GET.get('include_public') else []
    data = [{
        'id': d.id, 'name': d.name, 'is_public': d.is_public,
        'share_token': d.share_token or '', 'updated_at': d.updated_at.isoformat(),
    } for d in list(mine) + list(public)]
    return JsonResponse({'code':0,'data':{'items':data}})


@require_POST
@login_required
def api_dashboard_save(request):
    import json
    body = json.loads(request.body)
    name = body.get('name', f"我的仪表盘_{timezone.now().strftime('%m%d_%H%M')}")
    config = body.get('config', {})
    is_public = body.get('is_public', False)
    dash = SavedDashboard.objects.create(
        owner=request.user, name=name, config=config, is_public=is_public,
        share_token=secrets.token_urlsafe(16) if is_public else None,
    )
    return JsonResponse({'code':0,'data':{'id':dash.id,'share_token':dash.share_token}})


@require_GET
@login_required
def api_dashboard_load(request, dash_id):
    try:
        dash = SavedDashboard.objects.get(id=dash_id)
        if not dash.is_public and dash.owner != request.user:
            return JsonResponse({'code':1,'msg':'no permission'}, status=403)
        return JsonResponse({'code':0,'data':{'name':dash.name,'config':dash.config}})
    except SavedDashboard.DoesNotExist:
        return JsonResponse({'code':1,'msg':'not found'}, status=404)


@require_POST
@login_required
def api_dashboard_share(request, dash_id):
    import secrets
    try:
        dash = SavedDashboard.objects.get(id=dash_id, owner=request.user)
    except SavedDashboard.DoesNotExist:
        return JsonResponse({'code':1,'msg':'not found'})
    action = 'generate'
    dash.is_public = True
    dash.share_token = dash.share_token or secrets.token_urlsafe(16)
    dash.save(update_fields=['is_public','share_token'])
    return JsonResponse({'code':0,'data':{'share_token':dash.share_token}})


@require_http_methods(['DELETE'])
@login_required
def api_dashboard_delete(request, dash_id):
    try:
        dash = SavedDashboard.objects.get(id=dash_id, owner=request.user)
        dash.delete()
        return JsonResponse({'code':0})
    except SavedDashboard.DoesNotExist:
        return JsonResponse({'code':1,'msg':'not found'})


from cmdb.models import Server as CMDBServer
