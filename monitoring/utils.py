import logging
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

CACHE_PREFIX = 'monitoring:'
DETECTOR_CONFIG_CACHE_TTL = getattr(settings, 'MONITORING_CACHE_TTL', 300)
ANOMALY_STATS_CACHE_TTL = getattr(settings, 'ANOMALY_STATS_CACHE_TTL', 60)


def get_detector_config(detector_name):
    cache_key = f'{CACHE_PREFIX}det_config:{detector_name}'
    config = cache.get(cache_key)
    if config is not None:
        return config
    from monitoring.models import DetectorConfig
    try:
        config = DetectorConfig.objects.filter(
            detector_name=detector_name, is_enabled=True
        ).first()
        cache.set(cache_key, config, DETECTOR_CONFIG_CACHE_TTL)
        return config
    except Exception as e:
        logger.error(f"[Cache] 获取检测器配置失败: {e}")
        return None


def invalidate_detector_cache(detector_name=None):
    if detector_name:
        cache.delete(f'{CACHE_PREFIX}det_config:{detector_name}')
    else:
        for name in ['zscore','iqr','moving_avg','rate_of_change','composite']:
            cache.delete(f'{CACHE_PREFIX}det_config:{name}')


def get_anomaly_stats(days=7):
    cache_key = f'{CACHE_PREFIX}anomaly_stats:{days}'
    stats = cache.get(cache_key)
    if stats is not None:
        return stats
    from monitoring.models import AnomalyHistory
    from django.db.models import Count
    from django.utils import timezone
    since = timezone.now() - __import__('datetime').timedelta(days=days)
    qs = AnomalyHistory.objects.filter(detected_at__gte=since)
    stats = {
        'total': qs.count(),
        'by_severity': dict(qs.values_list('severity').annotate(cnt=Count('id')).values_list('severity', 'cnt')),
        'by_metric': dict(qs.values_list('metric_name').annotate(cnt=Count('id')).values_list('metric_name', 'cnt')),
    }
    cache.set(cache_key, stats, ANOMALY_STATS_CACHE_TTL)
    return stats


class BatchAnomalyWriter:
    def __init__(self, batch_size=50):
        self.batch_size = batch_size
        self._buffer = []

    def add(self, **kwargs):
        self._buffer.append(AnomalyHistory(**kwargs))
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self._buffer:
            return
        from django.db import transaction
        with transaction.atomic():
            AnomalyHistory.objects.bulk_create(self._buffer)
            count = len(self._buffer)
            self._buffer.clear()
            logger.info(f"[BatchAnomaly] 批量写入 {count} 条异常记录")
            return count


from monitoring.models import AnomalyHistory