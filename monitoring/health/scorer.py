import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg

from monitoring.models import (
    Server as CMDBServer, ServerMetric, AlertEvent,
    AnomalyHistory, HealthScore,
)

logger = logging.getLogger(__name__)


class HealthScorer:

    @staticmethod
    def score_server(server, scored_at=None):
        if scored_at is None:
            scored_at = timezone.now()

        cpu = HealthScorer._score_cpu(server)
        mem = HealthScorer._score_mem(server)
        disk = HealthScorer._score_disk(server)
        net = 100.0
        avail = HealthScorer._score_availability(server)

        alert_pen = HealthScorer._alert_penalty(server)
        anomaly_pen = HealthScorer._anomaly_penalty(server)

        overall = max(0.0,
            cpu * 0.25 + mem * 0.25 + disk * 0.20 +
            net * 0.15 + avail * 0.15 - alert_pen - anomaly_pen
        )

        grade = HealthScorer._score_to_grade(overall)

        return HealthScore.objects.create(
            server=server,
            scored_at=scored_at,
            overall_score=round(overall, 1),
            cpu_score=round(cpu, 1),
            mem_score=round(mem, 1),
            disk_score=round(disk, 1),
            network_score=round(net, 1),
            availability_score=round(avail, 1),
            alert_penalty=round(alert_pen, 1),
            anomaly_penalty=round(anomaly_pen, 1),
            grade=grade,
        )

    @staticmethod
    def _score_cpu(server):
        recent = ServerMetric.objects.filter(
            server=server, collected_at__gte=timezone.now() - timedelta(minutes=30)
        ).order_by('-collected_at')[:10]
        if not recent:
            return 80.0
        values = [r.cpu_usage for r in recent if r.cpu_usage is not None]
        if not values:
            return 80.0
        avg = sum(values) / len(values)
        score = 100.0
        if avg > 60:
            score -= (avg - 60) * 2.0
        if avg > 85:
            score -= (avg - 85) * 4.0
        return max(0.0, round(score, 1))

    @staticmethod
    def _score_mem(server):
        recent = ServerMetric.objects.filter(
            server=server, collected_at__gte=timezone.now() - timedelta(minutes=30)
        ).order_by('-collected_at')[:10]
        if not recent:
            return 85.0
        values = [r.mem_usage for r in recent if r.mem_usage is not None]
        if not values:
            return 85.0
        avg = sum(values) / len(values)
        score = 100.0
        if avg > 75:
            score -= (avg - 75) * 2.5
        if avg > 90:
            score -= (avg - 90) * 4.0
        return max(0.0, round(score, 1))

    @staticmethod
    def _score_disk(server):
        recent = ServerMetric.objects.filter(
            server=server, collected_at__gte=timezone.now() - timedelta(hours=6)
        ).order_by('-collected_at')[:20]
        if not recent:
            return 95.0
        values = [r.disk_usage for r in recent if r.disk_usage is not None]
        if not values:
            return 95.0
        avg = sum(values) / len(values)
        score = 100.0
        if avg > 80:
            score -= (avg - 80) * 3.0
        if avg > 95:
            score -= (avg - 95) * 8.0
        return max(0.0, round(score, 1))

    @staticmethod
    def _score_availability(server):
        if server.status == 'Running':
            return 100.0
        elif server.status == 'Maintenance':
            return 70.0
        else:
            return 0.0

    @staticmethod
    def _alert_penalty(server):
        since = timezone.now() - timedelta(hours=24)
        firing = AlertEvent.objects.filter(
            server=server, status='firing', fired_at__gte=since
        )
        penalty = 0.0
        for a in firing:
            base = 3.0 if a.severity in ['P2', 'P3'] else 6.0
            penalty += base
        return round(penalty, 1)

    @staticmethod
    def _anomaly_penalty(server):
        since = timezone.now() - timedelta(hours=24)
        anomalies = AnomalyHistory.objects.filter(
            server=server, detected_at__gte=since, severity='high'
        ).count()
        return anomalies * 5.0

    @staticmethod
    def _score_to_grade(score):
        if score >= 90: return 'A'
        if score >= 75: return 'B'
        if score >= 60: return 'C'
        if score >= 40: return 'D'
        return 'F'

    @staticmethod
    def scan_all_servers():
        servers = CMDBServer.objects.filter(status='Running')
        results = []
        for s in servers:
            try:
                hs = HealthScorer.score_server(s)
                results.append({
                    'server_id': s.id, 'hostname': s.hostname,
                    'score': hs.overall_score, 'grade': hs.grade,
                })
            except Exception as e:
                logger.warning(f"[HealthScan] {s.hostname} 评分失败: {e}")
        logger.info(f"[HealthScan] 完成: {len(results)} 台服务器")
        return results

    @staticmethod
    def get_ranking(limit=20):
        latest_scores = {}
        scores_qs = HealthScore.objects.all().order_by('-scored_at')
        seen_servers = set()
        for hs in scores_qs:
            if hs.server_id not in seen_servers:
                latest_scores[hs.server_id] = hs
                seen_servers.add(hs.server_id)
                if len(seen_servers) >= limit * 2:
                    break

        ranked = sorted(latest_scores.values(), key=lambda x: x.overall_score)
        return [{
            'rank': i + 1,
            'server_id': hs.server_id,
            'hostname': hs.server.hostname,
            'score': hs.overall_score,
            'grade': hs.grade,
            'scored_at': hs.scored_at.isoformat(),
        } for i, hs in enumerate(ranked[:limit])]

    @staticmethod
    def get_history(server_id, days=7):
        since = timezone.now() - timedelta(days=days)
        qs = HealthScore.objects.filter(
            server_id=server_id, scored_at__gte=since
        ).order_by('scored_at')
        return [{
            'score': hs.overall_score,
            'grade': hs.grade,
            'cpu': hs.cpu_score,
            'mem': hs.mem_score,
            'disk': hs.disk_score,
            'time': hs.scored_at.isoformat(),
        } for h in qs]
