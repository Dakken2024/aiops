import logging
from collections import defaultdict
from datetime import timedelta
from django.utils import timezone
from django.db.models import Q

from monitoring.models import (
    AlertEvent, AlertGroup, AlertCorrelationRule,
)

logger = logging.getLogger(__name__)

CORRELATION_WINDOW_SECONDS = 60


class Correlator:

    @staticmethod
    def find_active_clusters():
        since = timezone.now() - timedelta(seconds=CORRELATION_WINDOW_SECONDS)
        firing_events = list(AlertEvent.objects.filter(
            status='firing', fired_at__gte=since
        ).select_related('rule', 'server').order_by('fired_at'))

        if not firing_events:
            return []

        clusters = []
        used = set()

        for i, anchor in enumerate(firing_events):
            if id(anchor) in used:
                continue
            cluster = [anchor]
            used.add(id(anchor))
            for j, candidate in enumerate(firing_events):
                if i == j or id(candidate) in used:
                    continue
                if Correlator._is_related(anchor, candidate):
                    cluster.append(candidate)
                    used.add(id(candidate))

            if len(cluster) >= 2:
                clusters.append(cluster)

        return clusters

    @staticmethod
    def _is_related(a: AlertEvent, b: AlertEvent) -> bool:
        if a.server_id and a.server_id == b.server_id:
            time_diff = abs((a.fired_at - b.fired_at).total_seconds())
            if time_diff <= CORRELATION_WINDOW_SECONDS:
                return True

        if a.metric_name == b.metric_name and time_diff <= CORRELATION_WINDOW_SECONDS * 3:
            return True

        causal_pairs = [
            ('cpu_usage', 'mem_usage'),
            ('cpu_usage', 'load_1min'),
            ('disk_usage', 'net_in'),
            ('cpu_usage', 'load_1min'),
        ]
        pair_key = (a.metric_name, b.metric_name)
        rev_key = (b.metric_name, a.metric_name)
        if pair_key in causal_pairs or rev_key in causal_pairs:
            time_diff = abs((a.fired_at - b.fired_at).total_seconds())
            if 0 < time_diff <= CORRELATION_WINDOW_SECONDS * 5:
                return True

        return False

    @staticmethod
    def infer_root_cause(cluster):
        if not cluster or len(cluster) < 2:
            return None, [], 0.0

        severity_order = {'P0': 4, 'P1': 3, 'P2': 2, 'P3': 1}
        sorted_cluster = sorted(
            cluster,
            key=lambda e: (-severity_order.get(e.severity, 0), e.fired_at)
        )

        root_candidate = sorted_cluster[0]
        confidence = min(0.95, 0.6 + len(cluster) * 0.08)

        rule_match = Correlator._match_correlation_rules(cluster)
        if rule_match:
            root_candidate = rule_match.get('root_event', root_candidate)
            confidence = max(confidence, rule_match.get('confidence', 0.7))

        related_ids = [e.id for e in cluster if e.id != root_candidate.id]
        return root_candidate, related_ids, round(confidence, 2)

    @staticmethod
    def _match_correlation_rules(cluster):
        active_rules = AlertCorrelationRule.objects.filter(is_active=True)
        metrics_in_cluster = {e.metric_name for e in cluster}
        severities_in_cluster = {e.severity for e in cluster}

        for rule in active_rules:
            patterns = rule.trigger_patterns or {}
            match_metrics = patterns.get('metrics', [])
            match_severities = patterns.get('severities', [])

            if match_metrics and set(match_metrics) & metrics_in_cluster:
                if not match_severities or set(match_severities) & severities_in_cluster:
                    earliest = min(cluster, key=lambda e: e.fired_at)
                    return {
                        'root_event': earliest,
                        'confidence': rule.confidence_weight,
                        'rule_name': rule.name,
                        'hint': rule.root_cause_hint,
                        'action': rule.suggested_action,
                    }

        return None

    @staticmethod
    def get_correlation_summary():
        clusters = Correlator.find_active_clusters()
        results = []
        for cluster in clusters:
            root, related_ids, conf = Correlator.infer_root_cause(cluster)
            results.append({
                'cluster_size': len(cluster),
                'root_alert_id': root.id if root else None,
                'root_rule_name': root.rule.name if root and root.rule else '',
                'root_server': root.server.hostname if root and root.server else '',
                'related_count': len(related_ids),
                'confidence': conf,
                'alerts': [{
                    'id': e.id, 'rule': e.rule.name, 'severity': e.severity,
                    'metric': e.metric_name, 'server': e.server.hostname if e.server else '',
                    'fired_at': e.fired_at.isoformat(),
                } for e in sorted(cluster, key=lambda x: x.fired_at)],
            })
        return results

    @classmethod
    def correlate_metrics_logs(cls, alert_event, window_minutes=5):
        from monitoring.models import LogEntry

        if not alert_event.server:
            return []

        since = alert_event.fired_at - timedelta(minutes=window_minutes)
        until = alert_event.fired_at + timedelta(minutes=window_minutes)

        return list(LogEntry.objects.filter(
            server=alert_event.server,
            timestamp__gte=since,
            timestamp__lte=until,
            level__in=('ERROR', 'WARN', 'CRIT', 'ALERT', 'EMERG'),
        ).order_by('-timestamp').values('timestamp', 'level', 'source', 'message')[:20])

    @classmethod
    def correlate_metrics_traces(cls, alert_event, window_minutes=5):
        from monitoring.models import TraceSpan

        if not alert_event.server:
            return []

        since = alert_event.fired_at - timedelta(minutes=window_minutes)
        until = alert_event.fired_at + timedelta(minutes=window_minutes)

        error_spans = list(TraceSpan.objects.filter(
            server=alert_event.server,
            start_time__gte=since,
            start_time__lte=until,
            status='ERROR',
        ).order_by('-duration_ms').values(
            'trace_id', 'service_name', 'operation', 'duration_ms', 'error_message'
        )[:10])

        slow_threshold = 3000
        slow_spans = list(TraceSpan.objects.filter(
            server=alert_event.server,
            start_time__gte=since,
            start_time__lte=until,
            duration_ms__gte=slow_threshold,
        ).exclude(status='ERROR').order_by('-duration_ms').values(
            'trace_id', 'service_name', 'operation', 'duration_ms'
        )[:10])

        return {'errors': error_spans, 'slow': slow_spans}

    @classmethod
    def find_similar_cases(cls, alert_event, top_k=3):
        from monitoring.models import CaseVector

        symptoms_text = cls._build_symptoms_text(alert_event)

        try:
            from monitoring.embedding.service import EmbeddingService
            service = EmbeddingService()
            query_vector = service.embed_text(symptoms_text)

            if query_vector:
                try:
                    from pgvector.django import L2Distance
                    cases = list(CaseVector.objects.annotate(
                        distance=L2Distance('symptom_vector', query_vector)
                    ).filter(distance__lt=1.0).order_by('distance')[:top_k].values(
                        'id', 'title', 'root_cause', 'remediation',
                        'confidence', 'effectiveness_score', 'usage_count', 'distance'
                    ))
                    return cases
                except Exception:
                    pass
        except Exception:
            pass

        return list(CaseVector.objects.filter(
            effectiveness_score__gte=0.5,
        ).order_by('-effectiveness_score')[:top_k].values(
            'id', 'title', 'root_cause', 'remediation',
            'confidence', 'effectiveness_score', 'usage_count'
        ))

    @classmethod
    def correlate_all(cls, alert_event):
        logs = cls.correlate_metrics_logs(alert_event)
        traces = cls.correlate_metrics_traces(alert_event)
        cases = cls.find_similar_cases(alert_event)

        return {
            'alert_id': alert_event.id,
            'server': alert_event.server.hostname if alert_event.server else None,
            'metric_name': alert_event.metric_name,
            'fired_at': alert_event.fired_at.isoformat(),
            'related_logs': logs,
            'related_traces': traces,
            'similar_cases': cases,
            'logs_count': len(logs),
            'trace_errors': len(traces.get('errors', [])) if isinstance(traces, dict) else 0,
            'trace_slow': len(traces.get('slow', [])) if isinstance(traces, dict) else 0,
            'cases_count': len(cases),
        }

    @staticmethod
    def _build_symptoms_text(alert_event):
        parts = []
        if alert_event.server:
            parts.append(f"服务器{alert_event.server.hostname}")
        if alert_event.metric_name:
            parts.append(f"指标{alert_event.metric_name}异常")
        if alert_event.current_value:
            parts.append(f"当前值{alert_event.current_value}")
        if alert_event.severity:
            parts.append(f"严重程度{alert_event.severity}")
        return ' '.join(parts) if parts else '未知异常'
