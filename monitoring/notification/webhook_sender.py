import hmac
import hashlib
import json
import logging
import time

import requests
from django.utils import timezone

logger = logging.getLogger(__name__)


class WebhookSender:
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def _compute_signature(self, body_str):
        if not self.endpoint.secret:
            return ''
        return hmac.new(
            self.endpoint.secret.encode('utf-8'),
            body_str.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()

    def send(self, event_type, payload):
        timestamp = timezone.now().isoformat()
        body = {
            'event_type': event_type,
            'timestamp': timestamp,
            'payload': payload,
        }
        body_str = json.dumps(body, ensure_ascii=False)
        signature = self._compute_signature(body_str)
        body['signature'] = signature

        headers = {
            'Content-Type': 'application/json',
        }
        if signature:
            headers['X-Webhook-Signature'] = f'sha256={signature}'

        try:
            resp = requests.post(
                self.endpoint.url,
                data=json.dumps(body, ensure_ascii=False),
                headers=headers,
                timeout=10,
            )
            success = 200 <= resp.status_code < 300
            self.endpoint.last_status = str(resp.status_code) if success else f'error_{resp.status_code}'
            self.endpoint.last_sent_at = timezone.now()
            self.endpoint.save(update_fields=['last_status', 'last_sent_at'])
            return success, resp.status_code
        except requests.RequestException as e:
            self.endpoint.last_status = 'error'
            self.endpoint.last_sent_at = timezone.now()
            self.endpoint.save(update_fields=['last_status', 'last_sent_at'])
            logger.error(f"[WebhookSender] {self.endpoint.name}: {e}")
            return False, 0

    def send_with_retry(self, event_type, payload, max_retries=3):
        delays = [1, 2, 4]
        for attempt in range(max_retries):
            success, status_code = self.send(event_type, payload)
            if success:
                return True, status_code
            if attempt < max_retries - 1:
                time.sleep(delays[attempt])
        return False, status_code if 'status_code' in dir() else 0


def dispatch_webhooks(event_type, payload):
    from monitoring.models import WebhookEndpoint

    endpoints = WebhookEndpoint.objects.filter(is_active=True)
    results = []
    for ep in endpoints:
        if event_type not in ep.events:
            continue
        sender = WebhookSender(ep)
        success, status_code = sender.send_with_retry(event_type, payload)
        results.append({
            'endpoint_id': ep.id,
            'endpoint_name': ep.name,
            'success': success,
            'status_code': status_code,
        })
    return results
