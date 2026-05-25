import logging
from datetime import timedelta, datetime

from celery import shared_task
from django.db.models import Count, Avg, Q

from tracing.models import Span, ServiceMap

logger = logging.getLogger(__name__)


@shared_task
def generate_service_map(hours_back=24):
    """
    从Span数据提取服务调用关系，生成服务拓扑图
    """
    try:
        since_time = datetime.now() - timedelta(hours=hours_back)
        
        spans_with_peer = Span.objects.filter(
            start_time__gte=since_time,
            attributes__has_key='peer.service'
        ).select_related('trace')
        
        call_map = {}
        
        for span in spans_with_peer:
            source_service = span.trace.name
            target_service = span.attributes.get('peer.service', '')
            
            if not source_service or not target_service:
                continue
            
            key = (source_service, target_service)
            if key not in call_map:
                call_map[key] = {
                    'count': 0,
                    'durations': []
                }
            call_map[key]['count'] += 1
            call_map[key]['durations'].append(span.duration_ms)
        
        for (source, target), data in call_map.items():
            avg_duration = sum(data['durations']) / len(data['durations']) if data['durations'] else 0
            
            service_map, created = ServiceMap.objects.update_or_create(
                service_name=source,
                target_service=target,
                defaults={
                    'call_count': data['count'],
                    'avg_duration_ms': avg_duration,
                    'last_seen': datetime.now(),
                }
            )
            
            if created:
                logger.info(f"[Topology] 新增服务调用: {source} -> {target}")
            else:
                logger.debug(f"[Topology] 更新服务调用: {source} -> {target} (×{data['count']})")
        
        ServiceMap.objects.filter(last_seen__lt=since_time).delete()
        
        return {'updated': len(call_map), 'cleaned': 0}
    
    except Exception as e:
        logger.error(f"[Topology] 生成服务拓扑失败: {e}")
        return {'error': str(e)}


@shared_task
def analyze_slow_endpoints(min_duration_ms=1000, hours_back=6):
    """
    分析慢接口，用于告警规则
    """
    from monitoring.models import AlertRule, AlertEvent
    from django.utils import timezone
    
    since_time = timezone.now() - timedelta(hours=hours_back)
    
    slow_spans = Span.objects.filter(
        duration_ms__gte=min_duration_ms,
        start_time__gte=since_time
    ).select_related('trace')
    
    slow_endpoints = {}
    
    for span in slow_spans:
        endpoint = span.name
        service = span.trace.name
        
        if service not in slow_endpoints:
            slow_endpoints[service] = {}
        if endpoint not in slow_endpoints[service]:
            slow_endpoints[service][endpoint] = {
                'count': 0,
                'total_duration': 0,
                'max_duration': 0
            }
        
        slow_endpoints[service][endpoint]['count'] += 1
        slow_endpoints[service][endpoint]['total_duration'] += span.duration_ms
        slow_endpoints[service][endpoint]['max_duration'] = max(
            slow_endpoints[service][endpoint]['max_duration'],
            span.duration_ms
        )
    
    rules = AlertRule.objects.filter(
        rule_type='tracing_slow',
        status='enabled'
    )
    
    for rule in rules:
        config = rule.condition_config
        threshold = config.get('threshold_ms', 1000)
        min_count = config.get('min_count', 5)
        
        for service, endpoints in slow_endpoints.items():
            for endpoint, stats in endpoints.items():
                avg_duration = stats['total_duration'] / stats['count']
                if avg_duration >= threshold and stats['count'] >= min_count:
                    message = f"服务 [{service}] 的接口 [{endpoint}] 响应缓慢，平均耗时 {avg_duration:.2f}ms，共 {stats['count']} 次调用"
                    
                    AlertEvent.objects.create(
                        rule=rule,
                        severity=rule.severity,
                        metric_name='trace.latency',
                        current_value=avg_duration,
                        threshold_value=threshold,
                        message=message,
                        detail={
                            'service': service,
                            'endpoint': endpoint,
                            'avg_duration_ms': avg_duration,
                            'max_duration_ms': stats['max_duration'],
                            'call_count': stats['count'],
                        }
                    )
    
    return {'analyzed': len(slow_endpoints)}


@shared_task
def analyze_error_rates(min_error_rate=0.1, hours_back=6):
    """
    分析错误率，用于告警规则
    """
    from monitoring.models import AlertRule, AlertEvent
    from django.utils import timezone
    
    since_time = timezone.now() - timedelta(hours=hours_back)
    
    span_stats = Span.objects.filter(
        start_time__gte=since_time
    ).select_related('trace').values(
        'trace__name'
    ).annotate(
        total=Count('id'),
        errors=Count('id', filter=models.Q(status_code='error'))
    )
    
    rules = AlertRule.objects.filter(
        rule_type='tracing_error',
        status='enabled'
    )
    
    for stat in span_stats:
        service = stat['trace__name']
        total = stat['total']
        errors = stat['errors']
        error_rate = errors / total if total > 0 else 0
        
        for rule in rules:
            config = rule.condition_config
            threshold = config.get('threshold', 0.1)
            min_total = config.get('min_total', 10)
            
            if error_rate >= threshold and total >= min_total:
                message = f"服务 [{service}] 错误率过高: {error_rate:.2%} ({errors}/{total})"
                
                AlertEvent.objects.create(
                    rule=rule,
                    severity=rule.severity,
                    metric_name='trace.error_rate',
                    current_value=error_rate,
                    threshold_value=threshold,
                    message=message,
                    detail={
                        'service': service,
                        'error_rate': error_rate,
                        'error_count': errors,
                        'total_count': total,
                    }
                )
    
    return {'analyzed': len(span_stats)}
