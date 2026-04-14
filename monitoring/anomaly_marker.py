import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count

logger = logging.getLogger(__name__)


class AnomalyMarkerService:

    @staticmethod
    def get_mark_points(server_id=None, metric_name='cpu_usage', days=1, limit=20):
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
        summary = {
            'total': qs.count(),
            'by_severity': dict(qs.values_list('severity').annotate(cnt=Count('id')).values_list('severity', 'cnt')),
            'by_metric': dict(qs.values_list('metric_name').annotate(cnt=Count('id')).values_list('metric_name', 'cnt')),
        }
        return {'timeline': timeline, 'summary': summary}

    @staticmethod
    def get_anomaly_detail(anomaly_id):
        from cmdb.models import ServerMetric
        try:
            history = AnomalyHistory.objects.select_related(
                'server', 'alert_event', 'alert_event__rule'
            ).get(id=anomaly_id)
        except AnomalyHistory.DoesNotExist:
            return None
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


from monitoring.models import AnomalyHistory