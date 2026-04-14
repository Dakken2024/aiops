import logging
import subprocess
from datetime import timedelta

from django.utils import timezone
from celery import shared_task

from monitoring.models import AlertEvent, RemediationAction, RemediationHistory

logger = logging.getLogger(__name__)


class RemediationEngine:

    @staticmethod
    def find_actions(alert_event: AlertEvent):
        return list(RemediationAction.objects.filter(
            is_active=True
        ).filter(
            severity_filter__contains=alert_event.severity
        ))

    @staticmethod
    def evaluate_and_execute(alert_event: AlertEvent):
        actions = RemediationEngine.find_actions(alert_event)
        if not actions:
            logger.debug(f"[Remediation] 告警{alert_event.id}无匹配修复动作")
            return []

        results = []
        for action in actions:
            if action.is_dangerous:
                history = RemediationHistory.objects.create(
                    alert_event=alert_event,
                    action=action,
                    status='pending',
                    output='[危险操作] 需人工确认后执行',
                )
                results.append({'action': action.name, 'status': 'needs_confirmation', 'history_id': history.id})
                logger.info(f"[Remediation] 危险动作需确认: {action.name}")
                continue

            try:
                history = RemediationHistory.objects.create(
                    alert_event=alert_event,
                    action=action,
                    status='running',
                )
                execute_remediation_task.delay(history.id)
                results.append({'action': action.name, 'status': 'dispatched', 'history_id': history.id})
            except Exception as e:
                logger.error(f"[Remediation] 创建修复记录失败: {e}")
                results.append({'action': action.name, 'status': 'error', 'error': str(e)})

        return results


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def execute_remediation_task(history_id):
    from monitoring.models import RemediationHistory

    try:
        history = RemediationHistory.objects.select_related('action', 'alert_event').get(id=history_id)
    except RemediationHistory.DoesNotExist:
        logger.error(f"[RemediationTask] 记录不存在: id={history_id}")
        return {'status': 'not_found'}

    action = history.action
    timeout = action.timeout_seconds

    try:
        cmd = RemediationEngine._render_command(action.target_command, history.alert_event)
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout
        )

        if result.returncode == 0:
            history.status = 'success'
            history.output = (result.stdout or '')[:2000]
            logger.info(f"[RemediationTask] 成功: {action.name} (exit={result.returncode})")
        else:
            history.status = 'failed'
            history.error_message = (result.stderr or result.stdout or '未知错误')[:1000]
            history.output = (result.stdout or '')[:2000]
            logger.warning(f"[RemediationTask] 失败: {action.name} (exit={result.returncode})")

    except subprocess.TimeoutExpired:
        history.status = 'timeout'
        history.error_message = f'执行超时 ({timeout}s)'
        logger.error(f"[RemediationTask] 超时: {action.name}")

    except Exception as e:
        history.status = 'failed'
        history.error_message = str(e)[:500]
        logger.error(f"[RemediationTask] 异常: {action.name} - {e}")

    finally:
        history.finished_at = timezone.now()
        history.save(update_fields=['status', 'output', 'error_message', 'finished_at'])

    return {
        'status': history.status,
        'action': action.name,
        'output': history.output[:200],
    }

    @staticmethod
    def _render_command(template, alert_event):
        replacements = {
            '{server_ip}': alert_event.server.ip_address if alert_event.server else '',
            '{hostname}': alert_event.server.hostname if alert_event.server else '',
            '{server_id}': str(alert_event.server_id or ''),
            '{metric}': alert_event.metric_name or '',
            '{value}': str(alert_event.current_value or ''),
            '{severity}': alert_event.severity or '',
        }
        result = template
        for key, val in replacements.items():
            result = result.replace(key, val)
        return result
