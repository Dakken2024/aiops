import logging
from datetime import timedelta

import numpy as np
from django.utils import timezone

logger = logging.getLogger(__name__)


class CapacityPredictor:

    @staticmethod
    def predict_full_date(server, metric_name, threshold=95.0):
        from cmdb.models import ServerMetric

        field_map = {
            'disk_usage': 'disk_usage',
            'mem_usage': 'mem_usage',
            'cpu_usage': 'cpu_usage',
        }
        field = field_map.get(metric_name)
        if not field:
            return {
                'metric': metric_name,
                'current_value': None,
                'daily_growth': 0.0,
                'predicted_full_date': None,
                'days_remaining': None,
            }

        seven_days_ago = timezone.now() - timedelta(days=7)
        qs = ServerMetric.objects.filter(
            server=server,
            created_at__gte=seven_days_ago,
        ).order_by('created_at').values_list('created_at', field)

        data = list(qs)
        if len(data) < 2:
            return {
                'metric': metric_name,
                'current_value': None,
                'daily_growth': 0.0,
                'predicted_full_date': None,
                'days_remaining': None,
            }

        timestamps = [d[0] for d in data]
        values = [float(d[1]) for d in data if d[1] is not None]

        if len(values) < 2:
            return {
                'metric': metric_name,
                'current_value': None,
                'daily_growth': 0.0,
                'predicted_full_date': None,
                'days_remaining': None,
            }

        epoch = timestamps[0]
        x = np.array([(t - epoch).total_seconds() / 86400.0 for t in timestamps[:len(values)]])
        y = np.array(values)

        coeffs = np.polyfit(x, y, 1)
        slope = coeffs[0]
        intercept = coeffs[1]

        current_value = values[-1]
        daily_growth = slope

        if daily_growth <= 0:
            return {
                'metric': metric_name,
                'current_value': round(current_value, 2),
                'daily_growth': round(daily_growth, 4),
                'predicted_full_date': None,
                'days_remaining': None,
            }

        days_remaining = (threshold - current_value) / daily_growth
        if days_remaining < 0:
            days_remaining = 0

        predicted_date = timezone.now().date() + timedelta(days=int(days_remaining))

        return {
            'metric': metric_name,
            'current_value': round(current_value, 2),
            'daily_growth': round(daily_growth, 4),
            'predicted_full_date': predicted_date.strftime('%Y-%m-%d'),
            'days_remaining': int(days_remaining),
        }

    @classmethod
    def scan_all_servers(cls):
        from cmdb.models import Server

        results = []
        servers = Server.objects.filter(status='Running')

        for server in servers:
            for metric_name in ['disk_usage', 'mem_usage']:
                try:
                    prediction = cls.predict_full_date(server, metric_name)
                    prediction['server_id'] = server.id
                    prediction['server_name'] = server.hostname
                    prediction['server_ip'] = server.ip_address
                    results.append(prediction)
                except Exception as e:
                    logger.error(f"[CapacityPredictor] {server.hostname} {metric_name}: {e}")

        return results
