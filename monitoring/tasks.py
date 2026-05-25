from datetime import timedelta

import logging
from celery import shared_task
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def broadcast_metrics():
    from cmdb.models import Server, ServerMetric
    
    channel_layer = get_channel_layer()
    
    servers = Server.objects.filter(status='Running')
    metrics_list = []
    
    for server in servers:
        try:
            latest = ServerMetric.objects.filter(server=server).order_by('-collected_at').first()
            if not latest:
                continue
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
                'collected_at': latest.collected_at.isoformat() if latest.collected_at else '',
            })
        except Exception as e:
            logger.debug(f"[Broadcast] {server.hostname}: {e}")
            continue
    
    if not metrics_list:
        return {'status': 'no_data'}
    
    cluster_avg = {
        'cpu': round(sum(m['cpu_usage'] for m in metrics_list) / len(metrics_list), 2),
        'mem': round(sum(m['mem_usage'] for m in metrics_list) / len(metrics_list), 2),
        'disk': round(sum(m['disk_usage'] for m in metrics_list) / len(metrics_list), 2),
    }
    
    payload = {
        'event_type': 'metrics_update',
        'timestamp': timezone.now().isoformat(),
        'servers': metrics_list,
        'cluster_avg': cluster_avg,
        'total_count': len(metrics_list),
    }
    
    try:
        async_to_sync(channel_layer.group_send)('monitoring', {
            'type': 'monitoring_event',
            'data': payload
        })
        logger.info(f"[Broadcast] 已推送 {len(metrics_list)} 台服务器指标")
    except Exception as e:
        logger.error(f"[Broadcast] 推送失败: {e}")
        return {'status': 'error', 'error': str(e)}
    
    return {'status': 'ok', 'count': len(metrics_list)}


@shared_task
def daily_health_scan():
    from monitoring.health.scorer import HealthScorer
    results = HealthScorer.scan_all_servers()
    logger.info(f"[HealthScan] 每日巡检完成: {len(results)} 台服务器")
    return {'scanned': len(results)}


@shared_task
def agent_liveness_check():
    from monitoring.agent.push_api import AgentPushHandler
    stale_agents = AgentPushHandler.check_agent_liveness(threshold_minutes=5)
    if not stale_agents:
        return {'status': 'all_healthy'}
    
    from monitoring.models import AlertRule, AlertEvent
    absence_rule = AlertRule.objects.filter(rule_type='absence').first()
    results = []
    for agent in stale_agents:
        if absence_rule and agent.server:
            event = AlertEvent.objects.create(
                rule=absence_rule,
                server=agent.server,
                severity='P2',
                status='firing',
                metric_name='agent_heartbeat',
                current_value='offline',
            )
            results.append({'agent': agent.name, 'server': agent.server.hostname})
    return {'stale_count': len(stale_agents), 'alerts_created': len(results)}


@shared_task
def on_alert_fired(alert_event_id):
    from monitoring.escalation.escalator import Escalator
    try:
        from monitoring.models import AlertEvent
        event = AlertEvent.objects.get(id=alert_event_id)
        scheduled = Escalator.schedule_escalation(event)
        logger.info(f"[AlertFired] 告警{alert_event_id} 升级调度完成: {len(scheduled)} 步骤")
        return {'scheduled_steps': len(scheduled)}
    except Exception as e:
        logger.error(f"[AlertFired] 升级调度失败: {e}")
        return {'error': str(e)}


@shared_task
def data_retention_cleanup():
    from cmdb.models import ServerMetric
    from monitoring.models import DataRetentionPolicy, MetricAggregation
    from django.db.models import Avg, Max, Min, Count
    from datetime import timedelta

    policies = DataRetentionPolicy.objects.filter(is_active=True)
    results = []

    for policy in policies:
        if policy.metric_type != 'raw':
            continue

        cutoff = timezone.now() - timedelta(days=policy.retention_days)
        expired_qs = ServerMetric.objects.filter(created_at__lt=cutoff)

        if not expired_qs.exists():
            results.append({'policy': policy.name, 'action': 'no_expired_data'})
            continue

        earliest = expired_qs.order_by('created_at').first().created_at
        latest = expired_qs.order_by('-created_at').first().created_at

        _aggregate_before_delete(expired_qs, policy.aggregation_interval, earliest, latest)

        count = expired_qs.count()
        expired_qs.delete()

        results.append({
            'policy': policy.name,
            'deleted': count,
            'aggregation_interval': policy.aggregation_interval,
        })
        logger.info(f"[DataRetention] {policy.name}: 删除{count}条, 聚合间隔={policy.aggregation_interval}")

    log_cutoff = timezone.now() - timedelta(days=7)
    deleted_logs = 0
    try:
        from monitoring.models import LogEntry
        deleted_logs, _ = LogEntry.objects.filter(created_at__lt=log_cutoff).delete()
        results.append({'policy': 'LogEntry-7d', 'deleted': deleted_logs})
    except Exception as e:
        logger.debug(f"[DataRetention] LogEntry清理失败: {e}")

    trace_cutoff = timezone.now() - timedelta(days=14)
    deleted_traces = 0
    try:
        from monitoring.models import TraceSpan
        deleted_traces, _ = TraceSpan.objects.filter(created_at__lt=trace_cutoff).delete()
        results.append({'policy': 'TraceSpan-14d', 'deleted': deleted_traces})
    except Exception as e:
        logger.debug(f"[DataRetention] TraceSpan清理失败: {e}")

    return {'policies_executed': len(results), 'details': results}


def _aggregate_before_delete(qs, interval, earliest, latest):
    from cmdb.models import ServerMetric
    from monitoring.models import MetricAggregation
    from django.db.models import Avg, Max, Min, Count
    from datetime import timedelta

    interval_minutes = {'5m': 5, '1h': 60, '1d': 1440}.get(interval, 60)
    chunk = timedelta(minutes=interval_minutes)

    server_ids = list(qs.values_list('server_id', flat=True).distinct())

    for sid in server_ids:
        server_qs = qs.filter(server_id=sid)
        metric_fields = ['cpu_usage', 'mem_usage', 'disk_usage', 'load_1min', 'net_in', 'net_out']

        for field in metric_fields:
            current = earliest
            while current < latest:
                next_boundary = current + chunk
                chunk_qs = server_qs.filter(
                    created_at__gte=current,
                    created_at__lt=next_boundary,
                )
                agg = chunk_qs.aggregate(
                    avg=Avg(field), max_val=Max(field),
                    min_val=Min(field), cnt=Count(field),
                )
                if agg['cnt'] and agg['avg'] is not None:
                    MetricAggregation.objects.get_or_create(
                        server_id=sid,
                        metric_type=field,
                        aggregation_interval=interval,
                        timestamp=current,
                        defaults={
                            'avg_value': round(agg['avg'], 2),
                            'max_value': round(agg['max_val'] or 0, 2),
                            'min_value': round(agg['min_val'] or 0, 2),
                            'sample_count': agg['cnt'],
                        },
                    )
                current = next_boundary


@shared_task
def cloud_metrics_sync():
    from cmdb.models import CloudAccount, ServerMetric
    from monitoring.models import CloudResource
    from monitoring.cloud_adapters import AdapterRegistry

    accounts = CloudAccount.objects.filter(is_active=True)
    results = []

    for account in accounts:
        adapter = AdapterRegistry.from_cloud_account(account)
        if not adapter:
            logger.warning(f"[CloudSync] 未找到适配器: {account.type}")
            continue

        resources = CloudResource.objects.filter(
            cloud_account=account, is_active=True
        )

        for resource in resources:
            try:
                metrics = adapter.fetch_metrics(
                    instance_id=resource.instance_id,
                    resource_type=resource.resource_type,
                )
                normalized = adapter.normalize(metrics)

                for m in normalized:
                    if resource.local_server:
                        ServerMetric.objects.create(
                            server=resource.local_server,
                            **{m['metric_name']: m['value']},
                            collected_at=m['timestamp'],
                        )

                resource.last_sync_at = timezone.now()
                resource.save(update_fields=['last_sync_at'])
                results.append({
                    'account': account.name,
                    'resource': resource.instance_name or resource.instance_id,
                    'metrics_count': len(normalized),
                })
            except Exception as e:
                logger.error(f"[CloudSync] {account.name}/{resource.instance_id}: {e}")
                results.append({
                    'account': account.name,
                    'resource': resource.instance_id,
                    'error': str(e)[:200],
                })

    logger.info(f"[CloudSync] 同步完成: {len(results)} 个资源")
    return {'synced': len(results), 'details': results[:50]}


@shared_task
def cloud_resources_sync():
    from cmdb.models import CloudAccount
    from monitoring.models import CloudResource
    from monitoring.cloud_adapters import AdapterRegistry

    accounts = CloudAccount.objects.filter(is_active=True)
    total_created = 0
    total_updated = 0

    for account in accounts:
        adapter = AdapterRegistry.from_cloud_account(account)
        if not adapter:
            continue

        try:
            remote_resources = adapter.fetch_resources()
        except Exception as e:
            logger.error(f"[CloudResSync] {account.name} 拉取失败: {e}")
            continue

        for rr in remote_resources:
            obj, created = CloudResource.objects.update_or_create(
                cloud_account=account,
                instance_id=rr.instance_id,
                defaults={
                    'instance_name': rr.instance_name,
                    'resource_type': rr.resource_type,
                    'region': rr.region,
                    'is_active': rr.status == 'Running',
                    'extra_config': rr.extra,
                },
            )
            if created:
                total_created += 1
            else:
                total_updated += 1

    logger.info(f"[CloudResSync] 完成: 新增{total_created} 更新{total_updated}")
    return {'created': total_created, 'updated': total_updated}


@shared_task
def collect_server_logs():
    from cmdb.models import Server
    from monitoring.models import LogEntry
    from monitoring.log_collector.ssh_collector import SSHLogCollector

    servers = Server.objects.filter(status='Running')
    results = []

    for server in servers:
        try:
            collector = SSHLogCollector(server)
            entries = collector.collect(lines=50)
            created = 0
            for entry in entries:
                if entry.get('level') in ('ERROR', 'WARN', 'CRIT', 'ALERT', 'EMERG'):
                    _, is_new = LogEntry.objects.get_or_create(
                        server=server,
                        timestamp=entry['timestamp'],
                        level=entry['level'],
                        message=entry['message'][:2000],
                        defaults={
                            'source': entry.get('source', 'syslog'),
                            'structured_data': entry.get('structured_data', {}),
                        },
                    )
                    if is_new:
                        created += 1
            results.append({'server': server.hostname, 'created': created})
        except Exception as e:
            logger.debug(f"[LogCollect] {server.hostname}: {e}")

    logger.info(f"[LogCollect] 完成: {len(results)} 台服务器")
    return {'servers': len(results), 'details': results[:20]}


@shared_task
def generate_log_vectors():
    from monitoring.models import LogEntry
    from monitoring.embedding.service import EmbeddingService

    entries = LogEntry.objects.filter(message_vector__isnull=True)[:50]
    if not entries:
        return {'processed': 0}

    service = EmbeddingService()
    processed = 0

    for entry in entries:
        vector = service.embed_text(entry.message)
        if vector:
            entry.message_vector = str(vector)
            entry.save(update_fields=['message_vector'])
            processed += 1

    logger.info(f"[LogVectors] 处理了 {processed}/{len(entries)} 条日志")
    return {'processed': processed}


@shared_task
def generate_case_vectors():
    from monitoring.models import CaseVector
    from monitoring.embedding.service import EmbeddingService

    cases = CaseVector.objects.filter(symptom_vector__isnull=True)[:20]
    if not cases:
        return {'processed': 0}

    service = EmbeddingService()
    processed = 0

    for case in cases:
        symptoms_text = case.symptoms
        vector = service.embed_text(symptoms_text)
        if vector:
            case.symptom_vector = str(vector)
            case.save(update_fields=['symptom_vector'])
            processed += 1

    logger.info(f"[CaseVectors] 处理了 {processed}/{len(cases)} 个案例")
    return {'processed': processed}


@shared_task
def mine_log_patterns():
    from monitoring.models import LogEntry, LogPattern
    from monitoring.log_collector.drain_miner import DrainLogMiner, detect_anomaly_patterns

    since = timezone.now() - timedelta(hours=1)
    entries = LogEntry.objects.filter(timestamp__gte=since).values(
        'message', 'level', 'source', 'timestamp'
    )[:5000]

    if not entries:
        return {'patterns_found': 0}

    log_data = list(entries)
    miner = DrainLogMiner()
    patterns = miner.mine(log_data)
    patterns = detect_anomaly_patterns(patterns)

    created = 0
    updated = 0
    for p in patterns:
        obj, is_new = LogPattern.objects.update_or_create(
            pattern_template=p['pattern_template'],
            level=p['level'],
            source=p['source'],
            defaults={
                'occurrence_count': p['occurrence_count'],
                'first_seen': p['first_seen'],
                'last_seen': p['last_seen'],
                'is_anomaly_pattern': p['is_anomaly'],
            },
        )
        if is_new:
            created += 1
        else:
            updated += 1

    logger.info(f"[LogPatterns] 新增{created} 更新{updated}")
    return {'patterns_found': len(patterns), 'created': created, 'updated': updated}


@shared_task
def generate_case_vector(case_id):
    from monitoring.models import CaseVector
    from monitoring.embedding.service import EmbeddingService

    try:
        case = CaseVector.objects.get(id=case_id)
        if not case.symptom_vector:
            service = EmbeddingService()
            vector = service.embed_text(case.symptoms)
            if vector:
                case.symptom_vector = str(vector)
                case.save(update_fields=['symptom_vector'])
    except CaseVector.DoesNotExist:
        pass


@shared_task
def predict_capacity():
    from monitoring.prediction.capacity_predictor import CapacityPredictor
    from monitoring.models import AlertRule, AlertEvent

    results = CapacityPredictor.scan_all_servers()
    logger.info(f"[CapacityPredict] 容量预测完成: {len(results)} 条预测")

    alert_count = 0
    for pred in results:
        days_remaining = pred.get('days_remaining')
        if days_remaining is not None and days_remaining <= 7:
            rule, _ = AlertRule.objects.get_or_create(
                name=f'capacity_forecast_{pred["metric"]}',
                defaults={
                    'rule_type': 'trend',
                    'severity': 'P1' if days_remaining <= 3 else 'P2',
                    'status': 'enabled',
                    'metric_name': pred['metric'],
                    'condition_config': {'direction': 'up'},
                },
            )
            AlertEvent.objects.create(
                rule=rule,
                server_id=pred.get('server_id'),
                severity='P1' if days_remaining <= 3 else 'P2',
                status='firing',
                metric_name='capacity_forecast',
                current_value=pred.get('current_value', 0),
                threshold_value=95.0,
                message=f"{pred.get('server_name','')} {pred['metric']} 预计{days_remaining}天后达到95% (当前{pred.get('current_value',0)}%, 日增{pred.get('daily_growth',0)}%)",
                detail=pred,
            )
            alert_count += 1

    logger.info(f"[CapacityPredict] 创建容量告警: {alert_count} 条")
    return {'predicted': len(results), 'alerts_created': alert_count}


@shared_task
def learn_baselines():
    from monitoring.baseline.smart_baseline import SmartBaselineLearner

    results = SmartBaselineLearner.learn_all_servers()
    logger.info(f"[BaselineLearn] 基线学习完成: {len(results)} 条")
    return {'learned': len(results)}