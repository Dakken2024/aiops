import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1)
def execute_escalation_step_task(self, alert_event_id, policy_id, step_index):
    from monitoring.models import AlertEvent, EscalationPolicy
    from .escalator import Escalator

    try:
        event = AlertEvent.objects.get(id=alert_event_id)
        if event.status != 'firing':
            logger.info(f"[EscalationTask] 告警已{event.status}, 跳过升级步骤")
            return {'status': 'skipped', 'reason': f'alert_{event.status}'}

        policy = EscalationPolicy.objects.get(id=policy_id)
        result = Escalator.execute_step(event, policy, step_index)
        logger.info(f"[EscalationTask] 步骤完成: policy={policy.name} step={step_index} → {result}")
        return result

    except AlertEvent.DoesNotExist:
        return {'status': 'alert_not_found'}
    except EscalationPolicy.DoesNotExist:
        return {'status': 'policy_not_found'}
    except Exception as e:
        logger.error(f"[EscalationTask] 执行失败: {e}", exc_info=True)
        raise self.retry(exc=e)
