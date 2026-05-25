import logging
from datetime import timedelta

import numpy as np
from django.utils import timezone

logger = logging.getLogger(__name__)


class SmartBaselineLearner:

    @staticmethod
    def learn_daily_baseline(server_id, metric_name):
        from cmdb.models import Server, ServerMetric
        from monitoring.models import MetricBaseline

        try:
            server = Server.objects.get(id=server_id)
        except Server.DoesNotExist:
            return []

        seven_days_ago = timezone.now() - timedelta(days=7)
        field_map = {
            'cpu_usage': 'cpu_usage',
            'mem_usage': 'mem_usage',
            'disk_usage': 'disk_usage',
            'load_1min': 'load_1min',
            'net_in': 'net_in',
            'net_out': 'net_out',
        }
        field = field_map.get(metric_name)
        if not field:
            return []

        qs = ServerMetric.objects.filter(
            server=server,
            created_at__gte=seven_days_ago,
        ).order_by('created_at').values_list('created_at', field)

        data = list(qs)
        if not data:
            return []

        hourly_data = {}
        for ts, val in data:
            if val is None:
                continue
            hour = ts.hour
            hourly_data.setdefault(hour, []).append(float(val))

        results = []
        for hour, values in hourly_data.items():
            if len(values) < 2:
                continue
            arr = np.array(values)
            avg = float(np.mean(arr))
            std = float(np.std(arr))

            obj, created = MetricBaseline.objects.update_or_create(
                server=server,
                metric_name=metric_name,
                hour_of_day=hour,
                weekday__isnull=True,
                defaults={
                    'avg_value': round(avg, 4),
                    'std_dev': round(std, 4),
                    'sample_count': len(values),
                    'weekday': None,
                },
            )
            results.append({
                'server_id': server_id,
                'metric_name': metric_name,
                'hour_of_day': hour,
                'weekday': None,
                'avg': round(avg, 4),
                'std': round(std, 4),
                'sample_count': len(values),
            })

        return results

    @staticmethod
    def learn_weekly_baseline(server_id, metric_name):
        from cmdb.models import Server, ServerMetric
        from monitoring.models import MetricBaseline

        try:
            server = Server.objects.get(id=server_id)
        except Server.DoesNotExist:
            return []

        four_weeks_ago = timezone.now() - timedelta(days=28)
        field_map = {
            'cpu_usage': 'cpu_usage',
            'mem_usage': 'mem_usage',
            'disk_usage': 'disk_usage',
            'load_1min': 'load_1min',
            'net_in': 'net_in',
            'net_out': 'net_out',
        }
        field = field_map.get(metric_name)
        if not field:
            return []

        qs = ServerMetric.objects.filter(
            server=server,
            created_at__gte=four_weeks_ago,
        ).order_by('created_at').values_list('created_at', field)

        data = list(qs)
        if not data:
            return []

        weekly_data = {}
        for ts, val in data:
            if val is None:
                continue
            weekday = ts.weekday()
            hour = ts.hour
            key = (weekday, hour)
            weekly_data.setdefault(key, []).append(float(val))

        results = []
        for (weekday, hour), values in weekly_data.items():
            if len(values) < 2:
                continue
            arr = np.array(values)
            avg = float(np.mean(arr))
            std = float(np.std(arr))

            obj, created = MetricBaseline.objects.update_or_create(
                server=server,
                metric_name=metric_name,
                hour_of_day=hour,
                weekday=weekday,
                defaults={
                    'avg_value': round(avg, 4),
                    'std_dev': round(std, 4),
                    'sample_count': len(values),
                },
            )
            results.append({
                'server_id': server_id,
                'metric_name': metric_name,
                'hour_of_day': hour,
                'weekday': weekday,
                'avg': round(avg, 4),
                'std': round(std, 4),
                'sample_count': len(values),
            })

        return results

    @staticmethod
    def get_baseline(server_id, metric_name, hour, weekday=None):
        from monitoring.models import MetricBaseline

        try:
            if weekday is not None:
                baseline = MetricBaseline.objects.get(
                    server_id=server_id,
                    metric_name=metric_name,
                    hour_of_day=hour,
                    weekday=weekday,
                )
            else:
                baseline = MetricBaseline.objects.filter(
                    server_id=server_id,
                    metric_name=metric_name,
                    hour_of_day=hour,
                    weekday__isnull=True,
                ).first()

            if baseline is None:
                return None

            upper = baseline.avg_value + 3 * baseline.std_dev
            lower = baseline.avg_value - 3 * baseline.std_dev
            if lower < 0:
                lower = 0

            return {
                'avg': round(baseline.avg_value, 4),
                'std': round(baseline.std_dev, 4),
                'upper': round(upper, 4),
                'lower': round(lower, 4),
            }
        except MetricBaseline.DoesNotExist:
            return None

    @classmethod
    def learn_all_servers(cls):
        from cmdb.models import Server

        results = []
        servers = Server.objects.filter(status='Running')
        metric_names = ['cpu_usage', 'mem_usage', 'disk_usage']

        for server in servers:
            for metric_name in metric_names:
                try:
                    daily = cls.learn_daily_baseline(server.id, metric_name)
                    results.extend(daily)
                    weekly = cls.learn_weekly_baseline(server.id, metric_name)
                    results.extend(weekly)
                except Exception as e:
                    logger.error(f"[BaselineLearn] {server.hostname} {metric_name}: {e}")

        return results
