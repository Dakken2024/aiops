import logging
import secrets
from datetime import datetime
from django.utils import timezone

from monitoring.models import AgentToken, ServerMetric

logger = logging.getLogger(__name__)


def generate_token():
    return secrets.token_urlsafe(48)


class AgentPushHandler:

    @staticmethod
    def authenticate(token_str):
        try:
            return AgentToken.objects.select_related('server').get(
                token=token_str, is_active=True
            )
        except AgentToken.DoesNotExist:
            return None

    @staticmethod
    def push_metrics(agent_token, payload):
        hostname = payload.get('hostname', '')
        metrics_list = payload.get('metrics', [])
        tags = payload.get('tags', {})

        if not metrics_list:
            return {'accepted': 0, 'errors': ['empty_metrics']}

        if len(metrics_list) > 100:
            return {'accepted': 0, 'errors': ['exceeds_max_100']}

        server = agent_token.server
        accepted = 0
        errors = []
        metric_fields = {
            'cpu_usage', 'mem_usage', 'disk_usage',
            'load_1min', 'load_5min', 'load_15min',
            'net_in', 'net_out', 'conn_count',
        }

        for m in metrics_list[:100]:
            metric_name = m.get('metric', '')
            value = m.get('value')
            ts_str = m.get('timestamp')

            if not metric_name or value is None:
                errors.append(f"invalid:{metric_name}")
                continue

            try:
                ts = datetime.fromisoformat(ts_str) if ts_str else timezone.now()
            except (ValueError, TypeError):
                ts = timezone.now()

            kwargs = {'server': server, 'collected_at': ts}
            if metric_name in metric_fields:
                kwargs[metric_name] = float(value)
            else:
                errors.append(f"unknown_metric:{metric_name}")
                continue

            try:
                ServerMetric.objects.create(**kwargs)
                accepted += 1
            except Exception as e:
                errors.append(f"{metric_name}:{str(e)[:80]}")

        agent_token.last_seen_at = timezone.now()
        agent_token.save(update_fields=['last_seen_at'])

        logger.info(f"[AgentPush] {agent_token.name}: accepted={accepted} errors={len(errors)}")
        return {'accepted': accepted, 'errors': errors}

    @staticmethod
    def check_agent_liveness(threshold_minutes=5):
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(minutes=threshold_minutes)
        stale = AgentToken.objects.filter(
            is_active=True, last_seen_at__lt=cutoff
        ).select_related('server')
        return list(stale)
