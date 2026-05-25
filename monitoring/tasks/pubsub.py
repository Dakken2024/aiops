import json
import logging
import threading
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

METRIC_CHANNEL = 'monitoring:metric_updates'


def publish_metric_update(metric_data):
    """
    发布指标更新到 Redis channel
    
    :param metric_data: 指标数据字典，包含 server_id, metric_name, value, timestamp
    """
    try:
        channel = _get_redis_channel()
        if channel:
            message = json.dumps(metric_data)
            channel.publish(METRIC_CHANNEL, message)
            logger.debug(f"[PubSub] 已发布指标更新: {metric_data.get('metric_name')}")
    except Exception as e:
        logger.error(f"[PubSub] 发布失败: {e}")


def _get_redis_channel():
    """获取 Redis 发布连接"""
    try:
        return cache.client.get_client(write=True)
    except Exception as e:
        logger.error(f"[PubSub] 获取 Redis 连接失败: {e}")
        return None


class MetricChangeReceiver:
    """
    Redis Pub/Sub 指标变更订阅器
    
    订阅 metric_updates channel，当有新指标到达时触发回调
    """
    
    def __init__(self, callback=None):
        """
        :param callback: 收到指标更新时的回调函数，签名: callback(metric_data)
        """
        self.callback = callback
        self._subscriber = None
        self._thread = None
        self._running = False
    
    def start(self):
        """启动订阅线程"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        logger.info("[PubSub] 指标变更订阅器已启动")
    
    def stop(self):
        """停止订阅"""
        self._running = False
        if self._subscriber:
            try:
                self._subscriber.unsubscribe()
            except Exception as e:
                logger.error(f"[PubSub] 取消订阅失败: {e}")
    
    def _listen(self):
        """监听 Redis channel"""
        try:
            from redis import Redis
            import redis.exceptions
            
            redis_url = settings.REDIS_URL_CELERY_BROKER
            r = Redis.from_url(redis_url)
            self._subscriber = r.pubsub()
            self._subscriber.subscribe(METRIC_CHANNEL)
            
            for message in self._subscriber.listen():
                if not self._running:
                    break
                
                if message['type'] == 'message':
                    try:
                        metric_data = json.loads(message['data'].decode('utf-8'))
                        if self.callback:
                            self.callback(metric_data)
                    except json.JSONDecodeError as e:
                        logger.error(f"[PubSub] 消息解析失败: {e}")
                    except Exception as e:
                        logger.error(f"[PubSub] 回调执行失败: {e}")
        except redis.exceptions.ConnectionError as e:
            logger.error(f"[PubSub] Redis 连接失败: {e}")
        except Exception as e:
            logger.error(f"[PubSub] 监听异常: {e}")


def subscribe_metric_updates(callback):
    """
    便捷函数：创建并启动指标变更订阅器
    
    :param callback: 回调函数
    :return: MetricChangeReceiver 实例
    """
    receiver = MetricChangeReceiver(callback)
    receiver.start()
    return receiver