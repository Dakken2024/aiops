import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db.models import Avg, Max, Min, Count
from django.utils import timezone

logger = logging.getLogger(__name__)

METRIC_FIELDS = [
    'cpu_usage', 'mem_usage', 'disk_usage',
    'load_1min', 'net_in', 'net_out',
    'disk_read_rate', 'disk_write_rate',
]

INTERVAL_DELTA = {
    '5m': timedelta(minutes=5),
    '1h': timedelta(hours=1),
    '1d': timedelta(days=1),
}


def _get_trunc_func(interval):
    """根据数据库后端选择合适的时间截断函数。"""
    from django.db import connection
    vendor = connection.vendor
    if vendor == 'postgresql':
        from django.db.models.functions import Trunc
        return Trunc
    # SQLite / MySQL 使用自定义字符串分组
    return None


def _do_aggregate(interval, window_start, window_end):
    """
    对 ServerMetric 在 [window_start, window_end) 范围内按 interval 聚合，
    结果写入 MetricAggregation。
    使用数据库原生聚合避免内存溢出。
    """
    from cmdb.models import ServerMetric
    from monitoring.models import MetricAggregation

    delta = INTERVAL_DELTA.get(interval, timedelta(hours=1))
    trunc_cls = _get_trunc_func(interval)

    qs = ServerMetric.objects.filter(created_at__gte=window_start, created_at__lt=window_end)
    if not qs.exists():
        return 0

    # 按 server + 时间窗口 + 指标字段分组聚合
    # 为兼容多种数据库，采用遍历 server 的方式，每个 server 内按时间窗口批量聚合
    server_ids = list(qs.values_list('server_id', flat=True).distinct())
    total_created = 0

    for sid in server_ids:
        server_qs = qs.filter(server_id=sid)
        # 确定该 server 数据的时间边界
        agg_bounds = server_qs.aggregate(min_ts=Min('created_at'), max_ts=Max('created_at'))
        min_ts = agg_bounds['min_ts']
        max_ts = agg_bounds['max_ts']
        if not min_ts or not max_ts:
            continue

        current = min_ts.replace(second=0, microsecond=0)
        # 对齐到 interval 边界
        if interval == '5m':
            current = current.replace(minute=(current.minute // 5) * 5)
        elif interval == '1h':
            current = current.replace(minute=0)
        elif interval == '1d':
            current = current.replace(hour=0, minute=0)

        while current < max_ts:
            next_boundary = current + delta
            chunk_qs = server_qs.filter(created_at__gte=current, created_at__lt=next_boundary)

            for field in METRIC_FIELDS:
                # 数据库原生聚合
                agg = chunk_qs.aggregate(
                    avg=Avg(field),
                    max_val=Max(field),
                    min_val=Min(field),
                    cnt=Count(field),
                )
                if agg['cnt'] and agg['avg'] is not None:
                    obj, created = MetricAggregation.objects.update_or_create(
                        server_id=sid,
                        metric_type=field,
                        aggregation_interval=interval,
                        timestamp=current,
                        defaults={
                            'avg_value': round(agg['avg'], 2),
                            'max_value': round(agg['max_val'] or 0, 2),
                            'min_value': round(agg['min_val'] or 0, 2),
                            'sample_count': agg['cnt'],
                        },
                    )
                    if created:
                        total_created += 1
            current = next_boundary

    return total_created


@shared_task
def daily_cleanup():
    """
    每日清理任务：
    - 查询所有启用的 DataRetentionPolicy；
    - 对 raw 类型：删除 created_at 超过 retention_days 的 ServerMetric 记录；
    - 对聚合类型：删除过期的 MetricAggregation 记录；
    - 记录清理日志（删除数量、耗时）。
    """
    from monitoring.models import DataRetentionPolicy, MetricAggregation
    from cmdb.models import ServerMetric

    policies = DataRetentionPolicy.objects.filter(is_enabled=True)
    results = []
    start_time = time.time()

    for policy in policies:
        cutoff = timezone.now() - timedelta(days=policy.retention_days)

        if policy.metric_type == 'raw':
            expired_qs = ServerMetric.objects.filter(created_at__lt=cutoff)
            count = expired_qs.count()
            if count:
                expired_qs.delete()
            results.append({
                'policy': policy.name,
                'metric_type': policy.metric_type,
                'deleted': count,
                'cutoff': cutoff.isoformat(),
            })
            logger.info(f"[daily_cleanup] {policy.name}: 删除 {count} 条 ServerMetric (<{cutoff.isoformat()})")
        else:
            # 聚合数据过期清理
            expired_qs = MetricAggregation.objects.filter(
                aggregation_interval=policy.metric_type.replace('min', 'm').replace('hour', 'h').replace('day', 'd'),
                timestamp__lt=cutoff,
            )
            count = expired_qs.count()
            if count:
                expired_qs.delete()
            results.append({
                'policy': policy.name,
                'metric_type': policy.metric_type,
                'deleted': count,
                'cutoff': cutoff.isoformat(),
            })
            logger.info(f"[daily_cleanup] {policy.name}: 删除 {count} 条 MetricAggregation (<{cutoff.isoformat()})")

    elapsed = round(time.time() - start_time, 2)
    logger.info(f"[daily_cleanup] 完成，耗时 {elapsed}s，详情: {results}")
    return {'elapsed_seconds': elapsed, 'details': results}


@shared_task
def aggregate_metrics_5m():
    """每 5 分钟聚合最近 10 分钟内的原始指标。"""
    now = timezone.now()
    window_end = now.replace(second=0, microsecond=0)
    window_start = window_end - timedelta(minutes=10)
    total = _do_aggregate('5m', window_start, window_end)
    logger.info(f"[aggregate_metrics_5m] 聚合完成，新增 {total} 条 5m 记录")
    return {'interval': '5m', 'created': total}


@shared_task
def aggregate_metrics_1h():
    """每小时聚合最近 2 小时内的原始指标。"""
    now = timezone.now()
    window_end = now.replace(minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(hours=2)
    total = _do_aggregate('1h', window_start, window_end)
    logger.info(f"[aggregate_metrics_1h] 聚合完成，新增 {total} 条 1h 记录")
    return {'interval': '1h', 'created': total}


@shared_task
def aggregate_metrics_1d():
    """每天聚合最近 2 天的原始指标。"""
    now = timezone.now()
    window_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_start = window_end - timedelta(days=2)
    total = _do_aggregate('1d', window_start, window_end)
    logger.info(f"[aggregate_metrics_1d] 聚合完成，新增 {total} 条 1d 记录")
    return {'interval': '1d', 'created': total}
