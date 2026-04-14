import hashlib
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count

from monitoring.models import AlertEvent, AlertGroup

logger = logging.getLogger(__name__)

AGGREGATE_WINDOW_MINUTES = 15
STORM_THRESHOLD_PER_SERVER = 20
STORM_WINDOW_MINUTES = 5


class AlertAggregator:

    @staticmethod
    def fingerprint(rule_id, server_id, metric_name):
        raw = f"{rule_id}:{server_id or 0}:{metric_name}"
        return hashlib.md5(raw.encode()).hexdigest()

    @staticmethod
    def aggregate(event: AlertEvent) -> AlertGroup:
        fp = AlertAggregator.fingerprint(
            event.rule_id,
            event.server_id if event.server else None,
            event.metric_name
        )

        window_ago = timezone.now() - timedelta(minutes=AGGREGATE_WINDOW_MINUTES)
        group = AlertGroup.objects.filter(
            fingerprint=fp, status='firing',
            last_fired_at__gte=window_ago
        ).first()

        if group:
            group.alert_count += 1
            group.last_fired_at = timezone.now()
            if _severity_rank(event.severity) > _severity_rank(group.severity):
                group.severity = event.severity
            group.save(update_fields=['alert_count', 'last_fired_at', 'severity'])
            logger.info(f"[Aggregator] 聚合到已有组: {group.name} (count={group.alert_count})")
        else:
            server_name = event.server.hostname if event.server else 'Unknown'
            group_name = f"[{event.severity}] {event.rule.name} — {server_name}"
            group = AlertGroup.objects.create(
                name=group_name,
                fingerprint=fp,
                status='firing',
                severity=event.severity,
                alert_count=1,
            )
            logger.info(f"[Aggregator] 新建聚合组: {group.name}")

        return group

    @staticmethod
    def check_storm(server_id) -> bool:
        if not server_id:
            return False
        since = timezone.now() - timedelta(minutes=STORM_WINDOW_MINUTES)
        count = AlertEvent.objects.filter(
            server_id=server_id, fired_at__gte=since
        ).count()
        is_storm = count >= STORM_THRESHOLD_PER_SERVER
        if is_storm:
            logger.warning(f"[Storm] 服务器ID={server_id} 在{STORM_WINDOW_MINUTES}分钟内产生{count}条告警，触发风暴抑制")
        return is_storm

    @staticmethod
    def resolve_group_if_all_done(group: AlertGroup):
        remaining = AlertEvent.objects.filter(
            status='firing', rule__in=[group]
        ).exclude(pk__in=[]).count()
        if remaining == 0 and group.status == 'firing':
            group.status = 'resolved'
            group.resolved_at = timezone.now()
            group.save(update_fields=['status', 'resolved_at'])
            logger.info(f"[Aggregator] 聚合组已解决: {group.name}")


def _severity_rank(sev):
    ranks = {'P0': 4, 'P1': 3, 'P2': 2, 'P3': 1}
    return ranks.get(sev, 0)
