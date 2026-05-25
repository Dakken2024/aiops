"""
Redis 时序数据缓存工具
用于异常检测时减少数据库查询
"""

import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


def get_redis_client():
    """获取 Redis 客户端"""
    try:
        from django_redis import get_redis_connection
        return get_redis_connection("default")
    except Exception:
        import redis
        return redis.Redis(
            host=getattr(settings, 'REDIS_HOST', 'localhost'),
            port=getattr(settings, 'REDIS_PORT', 6379),
            password=getattr(settings, 'REDIS_PASSWORD', None),
            db=2,  # 使用 db2 避免与 Celery/Channels 冲突
            decode_responses=True
        )


class RedisTimeSeriesCache:
    """
    时序数据 Redis 缓存
    
    缓存结构:
        key: ts:metric:{server_id}:{metric_name}
        value: 有序集合 (zset)，score 为时间戳，member 为 JSON 序列化的指标值
    """
    
    PREFIX = "ts:metric"
    DEFAULT_TTL = 3600  # 1 小时
    MAX_ENTRIES = 1000  # 每个序列最大缓存条目数
    
    def __init__(self):
        self.redis = get_redis_client()
    
    def _key(self, server_id: int, metric_name: str) -> str:
        return f"{self.PREFIX}:{server_id}:{metric_name}"
    
    def add_metric(self, server_id: int, metric_name: str, value: float, 
                   timestamp: Optional[datetime] = None, ttl: int = None):
        """
        添加指标到缓存
        
        :param server_id: 服务器 ID
        :param metric_name: 指标名称
        :param value: 指标值
        :param timestamp: 时间戳，默认当前时间
        :param ttl: 过期时间（秒），默认 1 小时
        """
        try:
            key = self._key(server_id, metric_name)
            ts = timestamp or timezone.now()
            ts_float = ts.timestamp()
            
            data = json.dumps({
                'value': float(value),
                'timestamp': ts.isoformat(),
            })
            
            # 使用管道批量操作
            pipe = self.redis.pipeline()
            pipe.zadd(key, {data: ts_float})
            
            # 限制集合大小，移除旧数据
            pipe.zremrangebyrank(key, 0, -self.MAX_ENTRIES - 1)
            
            # 设置过期时间
            pipe.expire(key, ttl or self.DEFAULT_TTL)
            
            pipe.execute()
            
        except Exception as e:
            logger.warning(f"[RedisCache] 缓存指标失败: {e}")
    
    def get_series(self, server_id: int, metric_name: str, 
                   limit: int = 30) -> List[float]:
        """
        获取最近时序数据
        
        :param server_id: 服务器 ID
        :param metric_name: 指标名称
        :param limit: 返回最近 N 条
        :return: 指标值列表（时间升序）
        """
        try:
            key = self._key(server_id, metric_name)
            
            # 获取最近 limit 条（按 score 降序）
            results = self.redis.zrevrange(key, 0, limit - 1, withscores=False)
            
            if not results:
                return []
            
            # 解析并反转（时间升序）
            values = []
            for item in reversed(results):
                data = json.loads(item)
                values.append(data['value'])
            
            return values
            
        except Exception as e:
            logger.warning(f"[RedisCache] 读取缓存失败: {e}")
            return []
    
    def get_series_with_timestamps(self, server_id: int, metric_name: str,
                                    limit: int = 30) -> List[dict]:
        """
        获取带时间戳的时序数据
        
        :return: [{'value': float, 'timestamp': str}, ...]
        """
        try:
            key = self._key(server_id, metric_name)
            results = self.redis.zrevrange(key, 0, limit - 1, withscores=True)
            
            if not results:
                return []
            
            data_list = []
            for item, score in reversed(results):
                data = json.loads(item)
                data_list.append({
                    'value': data['value'],
                    'timestamp': data['timestamp'],
                    'ts': score,
                })
            
            return data_list
            
        except Exception as e:
            logger.warning(f"[RedisCache] 读取缓存失败: {e}")
            return []
    
    def clear_series(self, server_id: int, metric_name: str):
        """清除指定序列缓存"""
        try:
            key = self._key(server_id, metric_name)
            self.redis.delete(key)
        except Exception as e:
            logger.warning(f"[RedisCache] 清除缓存失败: {e}")
    
    def clear_all(self):
        """清除所有时序缓存"""
        try:
            pattern = f"{self.PREFIX}:*"
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
                logger.info(f"[RedisCache] 清除 {len(keys)} 个缓存键")
        except Exception as e:
            logger.warning(f"[RedisCache] 清除所有缓存失败: {e}")


# 全局缓存实例
ts_cache = RedisTimeSeriesCache()
