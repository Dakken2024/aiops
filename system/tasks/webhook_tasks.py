import hmac
import hashlib
import json
import logging
import time

import requests
from celery import shared_task
from django.utils import timezone

from system.models import WebhookEndpoint, WebhookLog

logger = logging.getLogger(__name__)


def compute_hmac_signature(secret: str, body: str) -> str:
    """计算 HMAC SHA256 签名"""
    if not secret:
        return ''
    return hmac.new(
        secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def exponential_backoff(attempt: int, base_delay: float = 1.0) -> float:
    """计算指数退避延迟（秒）"""
    return base_delay * (2 ** attempt)


@shared_task(bind=True, max_retries=3)
def send_webhook(self, endpoint_id: int, event_type: str, payload: dict):
    """
    发送 Webhook 任务
    
    :param endpoint_id: WebhookEndpoint 主键
    :param event_type: 事件类型
    :param payload: 要发送的数据
    """
    try:
        endpoint = WebhookEndpoint.objects.get(id=endpoint_id)
    except WebhookEndpoint.DoesNotExist:
        logger.error(f"WebhookEndpoint {endpoint_id} 不存在")
        return

    if not endpoint.enabled:
        logger.info(f"WebhookEndpoint {endpoint.name} 已禁用，跳过发送")
        return

    # 检查是否订阅了该事件类型
    if event_type not in endpoint.events:
        logger.debug(f"WebhookEndpoint {endpoint.name} 未订阅事件 {event_type}")
        return

    # 获取或创建日志记录
    log_entry, created = WebhookLog.objects.get_or_create(
        endpoint=endpoint,
        event_type=event_type,
        payload=payload,
        status__in=['pending', 'retrying'],
        defaults={
            'status': 'pending',
            'max_retries': 3,
        }
    )

    if not created:
        log_entry.retry_count += 1
        log_entry.status = 'retrying'
        log_entry.save()

    attempt = log_entry.retry_count

    # 构建请求体
    timestamp = timezone.now().isoformat()
    body_data = {
        'event_type': event_type,
        'timestamp': timestamp,
        'payload': payload,
    }
    body_str = json.dumps(body_data, ensure_ascii=False)

    # 计算签名
    signature = compute_hmac_signature(endpoint.secret, body_str)
    if signature:
        body_data['signature'] = signature

    # 构建请求头
    headers = {
        'Content-Type': 'application/json',
    }
    headers.update(endpoint.headers or {})
    if signature:
        headers['X-Webhook-Signature'] = f'sha256={signature}'

    try:
        logger.info(f"[Webhook] 发送 {event_type} 到 {endpoint.name} (尝试 {attempt + 1})")
        
        response = requests.request(
            method=endpoint.method,
            url=endpoint.url,
            data=json.dumps(body_data, ensure_ascii=False),
            headers=headers,
            timeout=30,
        )

        success = 200 <= response.status_code < 300
        
        # 更新日志
        log_entry.status = 'success' if success else 'failed'
        log_entry.response_status = response.status_code
        log_entry.response_body = response.text[:1000]
        log_entry.sent_at = timezone.now()
        log_entry.save()

        # 更新端点状态
        endpoint.last_status = str(response.status_code) if success else f'error_{response.status_code}'
        endpoint.last_sent_at = timezone.now()
        endpoint.save()

        if success:
            logger.info(f"[Webhook] 发送成功 {endpoint.name}: {response.status_code}")
            return {'success': True, 'status_code': response.status_code}
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            logger.error(f"[Webhook] 发送失败 {endpoint.name}: {error_msg}")
            log_entry.error_message = error_msg
            log_entry.save()

            # 失败时创建告警通知
            if attempt >= 3:
                create_webhook_failure_alert(endpoint, event_type, error_msg)

    except requests.RequestException as e:
        error_msg = str(e)
        logger.error(f"[Webhook] 请求异常 {endpoint.name}: {error_msg}")

        log_entry.status = 'failed'
        log_entry.error_message = error_msg
        log_entry.sent_at = timezone.now()
        log_entry.save()

        # 更新端点状态
        endpoint.last_status = 'error'
        endpoint.last_sent_at = timezone.now()
        endpoint.save()

        # 失败时创建告警通知（最后一次重试失败后）
        if attempt >= 3:
            create_webhook_failure_alert(endpoint, event_type, error_msg)

        # 如果还有重试机会，延迟重试
        if attempt < 3:
            delay = exponential_backoff(attempt)
            logger.info(f"[Webhook] {endpoint.name} 将在 {delay:.1f} 秒后重试 (第 {attempt + 2} 次)")
            self.retry(countdown=delay, exc=e)

    return {'success': False, 'error': error_msg}


def create_webhook_failure_alert(endpoint: WebhookEndpoint, event_type: str, error_msg: str):
    """创建 Webhook 发送失败告警"""
    from monitoring.models import AlertEvent, AlertRule
    
    try:
        # 查找或创建 Webhook 告警规则
        rule, _ = AlertRule.objects.get_or_create(
            name='Webhook 发送失败',
            defaults={
                'description': 'Webhook 出站请求失败告警',
                'rule_type': 'anomaly',
                'severity': 'P2',
                'status': 'enabled',
            }
        )

        # 创建告警事件
        alert = AlertEvent.objects.create(
            rule=rule,
            severity='P2',
            metric_name='webhook_failure',
            current_value=1,
            message=f"Webhook 发送失败: {endpoint.name} ({event_type})",
            detail={
                'endpoint_id': endpoint.id,
                'endpoint_name': endpoint.name,
                'endpoint_url': endpoint.url,
                'event_type': event_type,
                'error': error_msg,
            }
        )

        logger.warning(f"[Webhook] 创建告警: {alert.id} - {alert.message}")
    except Exception as e:
        logger.error(f"[Webhook] 创建告警失败: {e}")


def dispatch_webhooks(event_type: str, payload: dict):
    """
    向所有订阅该事件的 Webhook 端点发送通知
    
    :param event_type: 事件类型
    :param payload: 事件数据
    """
    endpoints = WebhookEndpoint.objects.filter(enabled=True)
    results = []
    
    for endpoint in endpoints:
        if event_type not in endpoint.events:
            continue
        
        # 异步发送
        send_webhook.delay(endpoint.id, event_type, payload)
        results.append({
            'endpoint_id': endpoint.id,
            'endpoint_name': endpoint.name,
            'status': 'queued',
        })
    
    return results
