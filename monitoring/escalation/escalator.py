import logging
from datetime import timedelta
from django.utils import timezone

from monitoring.models import AlertEvent, EscalationPolicy

logger = logging.getLogger(__name__)


class Escalator:

    @staticmethod
    def find_policies(alert_event):
        policies = EscalationPolicy.objects.filter(is_active=True)
        matched = []
        for p in policies:
            rules = p.match_rules or {}
            if not rules:
                matched.append(p)
                continue

            match = True
            if 'severities' in rules:
                if alert_event.severity not in rules['severities']:
                    match = False
            if 'rule_names' in rules:
                rule_name = alert_event.rule.name if alert_event.rule else ''
                if not any(rn.lower() in rule_name.lower() for rn in rules['rule_names']):
                    match = False
            if match:
                matched.append(p)
        return matched

    @staticmethod
    def schedule_escalation(alert_event):
        from .tasks import execute_escalation_step_task

        policies = Escalator.find_policies(alert_event)
        if not policies:
            return []

        scheduled = []
        for policy in policies:
            steps = policy.escalation_steps or []
            for idx, step in enumerate(steps):
                delay_min = step.get('delay_minutes', 0)
                eta = timezone.now() + timedelta(minutes=delay_min)

                try:
                    result = execute_escalation_step_task.apply_async(
                        args=[alert_event.id, policy.id, idx],
                        eta=eta,
                    )
                    scheduled.append({
                        'policy': policy.name,
                        'step_idx': idx,
                        'action': step.get('action', ''),
                        'eta': eta.isoformat(),
                        'task_id': result.id,
                    })
                except Exception as e:
                    logger.error(f"[Escalator] 调度失败: {e}")

        logger.info(f"[Escalator] 告警{alert_event.id} 已调度 {len(scheduled)} 个升级步骤")
        return scheduled

    @staticmethod
    def cancel_escalation(alert_event_id):
        from celery.result import AsyncResult
        pass

    @staticmethod
    def execute_step(alert_event, policy, step_index):
        steps = policy.escalation_steps or []
        if step_index >= len(steps):
            return {'status': 'no_such_step'}

        step = steps[step_index]
        action_type = step.get('action', '')

        if action_type == 'notify':
            return Escalator._do_notify(alert_event, step)
        elif action_type == 'escalate_severity':
            return Escalator._do_escalate_severity(alert_event, step)
        elif action_type == 'resolve':
            return Escalator._do_resolve(alert_event)
        else:
            return {'status': 'unknown_action', 'action': action_type}

    @staticmethod
    def _do_notify(alert_event, step):
        channels = step.get('channel', ['dingtalk'])
        targets = step.get('target', [])

        msg = f"[升级通知] 告警: {alert_event.rule.name}\n"
        msg += f"服务器: {alert_event.server.hostname if alert_event.server else '-'}\n"
        msg += f"级别: {alert_event.severity} | 指标: {alert_event.metric_name}\n"
        msg += f"当前值: {alert_event.current_value}\n"
        msg += f"触发时间: {alert_event.fired_at.strftime('%Y-%m-%d %H:%M')}"

        results = []
        for ch in channels:
            try:
                from monitoring.notification.channel_manager import send_notification
                send_notification(
                    channels=[ch],
                    title=f"告警升级 - {alert_event.severity}",
                    content=msg,
                    targets=targets,
                )
                results.append({'channel': ch, 'status': 'sent'})
            except Exception as e:
                results.append({'channel': ch, 'status': 'error', 'error': str(e)})

        return {'action': 'notify', 'results': results}

    @staticmethod
    def _do_escalate_severity(alert_event, step):
        new_sev = step.get('new_severity', 'P0')
        old_sev = alert_event.severity
        if old_sev != new_sev:
            alert_event.severity = new_sev
            alert_event.save(update_fields=['severity'])
            logger.info(f"[Escalator] 级别升级: {old_sev} → {new_sev} (event={alert_event.id})")
        return {'action': 'escalate_severity', 'old': old_sev, 'new': new_sev}

    @staticmethod
    def _do_resolve(alert_event):
        if alert_event.status == 'firing':
            alert_event.status = 'resolved'
            alert_event.resolved_at = timezone.now()
            alert_event.save(update_fields=['status', 'resolved_at'])
        return {'action': 'resolve', 'status': alert_event.status}
