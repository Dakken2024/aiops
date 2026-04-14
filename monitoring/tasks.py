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