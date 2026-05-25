import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from monitoring.models import RemediationHistory

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_dingtalk_callback(request):
    history_id = request.GET.get('history_id') or request.POST.get('history_id')
    action = request.GET.get('action') or request.POST.get('action')

    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            history_id = history_id or body.get('history_id')
            action = action or body.get('action')
        except (json.JSONDecodeError, TypeError):
            pass

    if not history_id or not action:
        return JsonResponse({'code': 1, 'msg': 'missing parameters'})

    try:
        history = RemediationHistory.objects.get(id=int(history_id))
    except (RemediationHistory.DoesNotExist, ValueError):
        return JsonResponse({'code': 1, 'msg': '记录不存在'}, status=404)

    if history.status not in ('pending_confirm', 'pending'):
        return JsonResponse({'code': 1, 'msg': '当前状态不允许操作'})

    if action == 'confirm':
        history.status = 'pending'
        history.save(update_fields=['status'])
        from monitoring.remediation.remediation_engine import execute_remediation_task
        execute_remediation_task.delay(history.id)
        logger.info(f"[DingTalk Callback] 确认执行: history_id={history.id}")
        return JsonResponse({'code': 0, 'data': {'id': history.id, 'status': 'executing'}})
    elif action == 'reject':
        history.status = 'cancelled'
        history.finished_at = timezone.now()
        history.save(update_fields=['status', 'finished_at'])
        logger.info(f"[DingTalk Callback] 拒绝执行: history_id={history.id}")
        return JsonResponse({'code': 0, 'data': {'id': history.id, 'status': 'cancelled'}})

    return JsonResponse({'code': 1, 'msg': 'invalid action'})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def api_wecom_callback(request):
    history_id = request.GET.get('history_id') or request.POST.get('history_id')
    action = request.GET.get('action') or request.POST.get('action')

    if request.method == 'POST':
        try:
            body = json.loads(request.body)
            history_id = history_id or body.get('history_id')
            action = action or body.get('action')
        except (json.JSONDecodeError, TypeError):
            pass

    if not history_id or not action:
        return JsonResponse({'code': 1, 'msg': 'missing parameters'})

    try:
        history = RemediationHistory.objects.get(id=int(history_id))
    except (RemediationHistory.DoesNotExist, ValueError):
        return JsonResponse({'code': 1, 'msg': '记录不存在'}, status=404)

    if history.status not in ('pending_confirm', 'pending'):
        return JsonResponse({'code': 1, 'msg': '当前状态不允许操作'})

    if action == 'confirm':
        history.status = 'pending'
        history.save(update_fields=['status'])
        from monitoring.remediation.remediation_engine import execute_remediation_task
        execute_remediation_task.delay(history.id)
        logger.info(f"[WeCom Callback] 确认执行: history_id={history.id}")
        return JsonResponse({'code': 0, 'data': {'id': history.id, 'status': 'executing'}})
    elif action == 'reject':
        history.status = 'cancelled'
        history.finished_at = timezone.now()
        history.save(update_fields=['status', 'finished_at'])
        logger.info(f"[WeCom Callback] 拒绝执行: history_id={history.id}")
        return JsonResponse({'code': 0, 'data': {'id': history.id, 'status': 'cancelled'}})

    return JsonResponse({'code': 1, 'msg': 'invalid action'})
