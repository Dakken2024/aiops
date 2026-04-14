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
