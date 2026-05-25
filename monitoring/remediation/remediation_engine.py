import logging
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
                ai_confidence = 0.0
                try:
                    anomaly = alert_event.anomaly_history
                    if anomaly and hasattr(anomaly, 'confidence'):
                        ai_confidence = anomaly.confidence or 0.0
                except Exception:
                    pass

                if ai_confidence >= 0.85:
                    history.decision_mode = 'auto_confirm'
                    history.save(update_fields=['decision_mode'])
                    execute_remediation_task.delay(history.id)
                else:
                    history.decision_mode = 'human_confirm'
                    history.status = 'pending_confirm'
                    history.save(update_fields=['decision_mode', 'status'])
                    logger.info(f"[Remediation] 置信度{ai_confidence:.2f}<0.85, 等待人工确认: action={action.name}")
                    try:
                        from monitoring.notification.interactive_card import send_interactive_card
                        diagnosis_result = {
                            'root_cause': '',
                            'suggestion': action.target_command,
                            'confidence': ai_confidence,
                        }
                        try:
                            anomaly = alert_event.anomaly_history
                            if anomaly:
                                diagnosis_result['root_cause'] = anomaly.ai_diagnosis or ''
                        except Exception:
                            pass
                        send_interactive_card(history.id, diagnosis_result)
                    except Exception as e:
                        logger.error(f"[Remediation] 推送交互卡片失败: {e}")
                results.append({'action': action.name, 'status': 'dispatched', 'history_id': history.id})
            except Exception as e:
                logger.error(f"[Remediation] 创建修复记录失败: {e}")
                results.append({'action': action.name, 'status': 'error', 'error': str(e)})

        return results

    @staticmethod
    def _validate_command(command):
        dangerous_patterns = [';', '|', '&', '$(', '`', '&&', '||']
        for pattern in dangerous_patterns:
            if pattern in command:
                return False
        return True

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

    @staticmethod
    def _create_case_vector(alert_event, diagnosis_result, remediation_action, success):
        from monitoring.models import CaseVector
        try:
            symptoms_parts = []
            if alert_event.server:
                symptoms_parts.append(f"服务器{alert_event.server.hostname}")
            if alert_event.metric_name:
                symptoms_parts.append(f"指标{alert_event.metric_name}异常")
            if alert_event.current_value:
                symptoms_parts.append(f"当前值{alert_event.current_value}")
            symptoms = ' '.join(symptoms_parts) if symptoms_parts else '未知异常'

            root_cause = ''
            if isinstance(diagnosis_result, dict):
                root_cause = diagnosis_result.get('root_cause', '')
            elif isinstance(diagnosis_result, str):
                root_cause = diagnosis_result[:500]

            remediation_desc = remediation_action.name if remediation_action else '未知修复'

            confidence = 0.0
            if isinstance(diagnosis_result, dict):
                confidence = float(diagnosis_result.get('confidence', 0.0))

            CaseVector.objects.create(
                title=f"{alert_event.metric_name or '异常'} - {alert_event.server.hostname if alert_event.server else '未知'}",
                symptoms=symptoms,
                root_cause=root_cause or '待分析',
                remediation=remediation_desc,
                confidence=confidence,
                effectiveness_score=0.5 if success else 0.2,
                usage_count=1,
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(f"[CaseVector] 创建失败: {e}")


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def execute_remediation_task(history_id):
    from monitoring.models import RemediationHistory

    try:
        history = RemediationHistory.objects.select_related('action', 'alert_event__server').get(id=history_id)
    except RemediationHistory.DoesNotExist:
        logger.error(f"[RemediationTask] 记录不存在: id={history_id}")
        return {'status': 'not_found'}

    action = history.action
    timeout = action.timeout_seconds
    server = history.alert_event.server if history.alert_event else None

    try:
        cmd = RemediationEngine._render_command(action.target_command, history.alert_event)

        if not RemediationEngine._validate_command(cmd):
            history.status = 'failed'
            history.error_message = '命令包含非法字符，已拒绝执行'
            history.finished_at = timezone.now()
            history.save(update_fields=['status', 'error_message', 'finished_at'])
            return {'status': 'failed', 'action': action.name, 'error': 'invalid_command'}

        if server:
            output, error, exit_code = _execute_via_ssh(server, cmd, timeout)
        else:
            history.status = 'failed'
            history.error_message = '无目标服务器'
            history.finished_at = timezone.now()
            history.save(update_fields=['status', 'error_message', 'finished_at'])
            return {'status': 'failed', 'action': action.name, 'error': 'no_server'}

        if exit_code == 0:
            history.status = 'success'
            history.output = (output or '')[:2000]
            logger.info(f"[RemediationTask] 成功: {action.name} (exit={exit_code})")
        else:
            history.status = 'failed'
            history.error_message = (error or output or '未知错误')[:1000]
            history.output = (output or '')[:2000]
            logger.warning(f"[RemediationTask] 失败: {action.name} (exit={exit_code})")

    except Exception as e:
        history.status = 'failed'
        history.error_message = str(e)[:500]
        logger.error(f"[RemediationTask] 异常: {action.name} - {e}")

    finally:
        history.finished_at = timezone.now()
        history.save(update_fields=['status', 'output', 'error_message', 'finished_at'])

    try:
        RemediationEngine._create_case_vector(
            alert_event=history.alert_event,
            diagnosis_result=None,
            remediation_action=history.action,
            success=(history.status == 'success'),
        )
    except Exception:
        pass

    return {
        'status': history.status,
        'action': action.name,
        'output': history.output[:200],
    }


def _execute_via_ssh(server, command, timeout=300):
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        connect_kwargs = {
            'hostname': server.ip_address,
            'port': server.port,
            'username': server.username,
            'timeout': min(timeout, 30),
        }
        if server.password:
            connect_kwargs['password'] = server.password
        client.connect(**connect_kwargs)
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        exit_code = stdout.channel.recv_exit_status()
        output = stdout.read().decode('utf-8', errors='replace')
        error = stderr.read().decode('utf-8', errors='replace')
        return output, error, exit_code
    except Exception as e:
        return '', str(e), -1
    finally:
        client.close()
