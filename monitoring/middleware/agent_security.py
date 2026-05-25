import hmac
import hashlib
import logging
import time

from django.http import JsonResponse

from monitoring.models import AgentToken

logger = logging.getLogger(__name__)

AGENT_PUSH_PATH = '/api/agent/push/'


class AgentSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        if not request.path.endswith(AGENT_PUSH_PATH):
            return None

        token_str = request.META.get('HTTP_X_AGENT_TOKEN', '')
        signature = request.META.get('HTTP_X_AGENT_SIGNATURE', '')
        timestamp_str = request.META.get('HTTP_X_AGENT_TIMESTAMP', '')

        if not token_str:
            return JsonResponse({'code': 1, 'msg': 'missing X-Agent-Token'}, status=401)

        if not signature:
            return JsonResponse({'code': 1, 'msg': 'missing X-Agent-Signature'}, status=401)

        if not timestamp_str:
            return JsonResponse({'code': 1, 'msg': 'missing X-Agent-Timestamp'}, status=401)

        try:
            ts = int(timestamp_str)
            now_ts = int(time.time())
            if abs(now_ts - ts) > 300:
                return JsonResponse({'code': 1, 'msg': 'timestamp expired'}, status=401)
        except (ValueError, TypeError):
            return JsonResponse({'code': 1, 'msg': 'invalid timestamp'}, status=401)

        try:
            token_obj = AgentToken.objects.select_related('server').get(
                token=token_str, is_active=True
            )
        except AgentToken.DoesNotExist:
            return JsonResponse({'code': 1, 'msg': 'invalid token'}, status=403)

        if token_obj.allowed_ips:
            client_ip = self._get_client_ip(request)
            if client_ip not in token_obj.allowed_ips:
                logger.warning(
                    f"[AgentSecurity] IP not allowed: token={token_obj.name}, ip={client_ip}"
                )
                return JsonResponse({'code': 1, 'msg': 'ip not allowed'}, status=403)

        if not token_obj.hmac_secret:
            return JsonResponse({'code': 1, 'msg': 'hmac secret not configured'}, status=403)

        body = request.body.decode('utf-8') if isinstance(request.body, bytes) else request.body
        expected = hmac.new(
            token_obj.hmac_secret.encode('utf-8'),
            f'{timestamp_str}.{body}'.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected, signature):
            logger.warning(
                f"[AgentSecurity] Invalid signature: token={token_obj.name}"
            )
            return JsonResponse({'code': 1, 'msg': 'invalid signature'}, status=403)

        request.agent_token = token_obj
        return None

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip or ''
