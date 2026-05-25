import logging
import secrets
import hmac
import hashlib
from datetime import datetime
from django.utils import timezone
from django.core.cache import cache

from monitoring.models import AgentToken, ServerMetric

logger = logging.getLogger(__name__)

INCREMENTAL_THRESHOLD_CACHE_KEY = 'agent:incremental_threshold:{}'
DEFAULT_INCREMENTAL_THRESHOLD = 5.0


def generate_token():
    return secrets.token_urlsafe(48)


def verify_signature(token, timestamp, body, signature):
    if not timestamp or not signature:
        return False
    try:
        ts = int(timestamp)
        now_ts = int(timezone.now().timestamp())
        if abs(now_ts - ts) > 300:
            return False
    except (ValueError, TypeError):
        return False
    expected = hmac.new(
        token.encode('utf-8'),
        f'{timestamp}.{body}'.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def _should_send_incremental(agent_token_id, metric_name, value, threshold=None):
    """
    判断指标是否应该发送（增量模式）
    
    :param agent_token_id: AgentToken ID
    :param metric_name: 指标名称
    :param value: 当前值
    :param threshold: 变化阈值（百分比）
    :return: True 表示应该发送，False 表示变化未超过阈值
    """
    if threshold is None:
        threshold = DEFAULT_INCREMENTAL_THRESHOLD
    
    cache_key = INCREMENTAL_THRESHOLD_CACHE_KEY.format(f"{agent_token_id}:{metric_name}")
    last_value = cache.get(cache_key)
    
    if last_value is None:
        cache.set(cache_key, value, timeout=3600)
        return True
    
    diff = abs(value - last_value)
    percent_change = (diff / max(abs(last_value), 0.0001)) * 100
    
    if percent_change >= threshold:
        cache.set(cache_key, value, timeout=3600)
        return True
    
    return False


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
    def push_metrics(agent_token, payload, incremental=False, incremental_threshold=None):
        """
        推送指标数据
        
        :param agent_token: AgentToken 对象
        :param payload: 包含 metrics 的字典
        :param incremental: 是否增量模式（仅发送变化超过阈值的指标）
        :param incremental_threshold: 增量阈值（百分比），默认 5.0%
        :return: 处理结果字典
        """
        hostname = payload.get('hostname', '')
        metrics_list = payload.get('metrics', [])
        tags = payload.get('tags', {})

        if not metrics_list:
            return {'accepted': 0, 'errors': ['empty_metrics'], 'skipped': 0}

        if len(metrics_list) > 100:
            return {'accepted': 0, 'errors': ['exceeds_max_100'], 'skipped': 0}

        server = agent_token.server
        accepted = 0
        skipped = 0
        errors = []
        metric_fields = {
            'cpu_usage', 'mem_usage', 'disk_usage',
            'load_1min', 'load_5min', 'load_15min',
            'net_in', 'net_out', 'conn_count',
            'disk_read_rate', 'disk_write_rate',
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

            if metric_name not in metric_fields:
                errors.append(f"unknown_metric:{metric_name}")
                continue

            try:
                float_value = float(value)
            except (ValueError, TypeError):
                errors.append(f"invalid_value:{metric_name}")
                continue

            if incremental:
                if not _should_send_incremental(agent_token.id, metric_name, float_value, incremental_threshold):
                    skipped += 1
                    continue

            kwargs = {'server': server, 'collected_at': ts}
            kwargs[metric_name] = float_value

            try:
                ServerMetric.objects.create(**kwargs)
                accepted += 1
                
                # 同步写入 Redis 时序缓存
                if server:
                    from monitoring.utils.redis_cache import ts_cache
                    ts_cache.add_metric(
                        server_id=server.id,
                        metric_name=metric_name,
                        value=float_value,
                        timestamp=ts
                    )
                
                from monitoring.tasks.pubsub import publish_metric_update
                publish_metric_update({
                    'server_id': server.id if server else None,
                    'server_hostname': server.hostname if server else hostname,
                    'metric_name': metric_name,
                    'value': float_value,
                    'timestamp': ts.isoformat(),
                })
            except Exception as e:
                errors.append(f"{metric_name}:{str(e)[:80]}")

        agent_token.last_seen_at = timezone.now()
        agent_token.save(update_fields=['last_seen_at'])

        logger.info(f"[AgentPush] {agent_token.name}: accepted={accepted} skipped={skipped} errors={len(errors)}")
        if accepted > 0 and server:
            try:
                from monitoring.engine.rule_evaluator import RuleEvaluator
                RuleEvaluator.evaluate_rules_for_server(server.id)
            except Exception as e:
                logger.warning(f"[AgentPush] 事件驱动评估失败: {e}")
        
        return {
            'accepted': accepted,
            'skipped': skipped,
            'errors': errors
        }

    @staticmethod
    def push_metrics_with_header(agent_token, payload, headers):
        """
        通过请求头判断增量模式的推送方法
        
        :param agent_token: AgentToken 对象
        :param payload: 包含 metrics 的字典
        :param headers: 请求头字典
        :return: 处理结果字典
        """
        incremental = headers.get('X-Incremental', 'false').lower() == 'true'
        threshold_header = headers.get('X-Incremental-Threshold')
        
        incremental_threshold = None
        if threshold_header:
            try:
                incremental_threshold = float(threshold_header)
            except ValueError:
                pass
        
        return AgentPushHandler.push_metrics(
            agent_token, payload,
            incremental=incremental,
            incremental_threshold=incremental_threshold
        )

    @staticmethod
    def check_agent_liveness(threshold_minutes=5):
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(minutes=threshold_minutes)
        stale = AgentToken.objects.filter(
            is_active=True, last_seen_at__lt=cutoff
        ).select_related('server')
        return list(stale)
