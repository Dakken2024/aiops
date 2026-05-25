import logging
import requests
from django.conf import settings

from monitoring.models import RemediationHistory
from system.models import SystemConfig

logger = logging.getLogger(__name__)


class DingTalkCardBuilder:

    def __init__(self, history_id, diagnosis_result, base_url):
        self.history_id = history_id
        self.diagnosis_result = diagnosis_result
        self.base_url = base_url

    def build(self):
        history = RemediationHistory.objects.select_related(
            'action', 'alert_event__server'
        ).get(id=self.history_id)

        root_cause = self.diagnosis_result.get('root_cause', '待分析')
        suggestion = self.diagnosis_result.get('suggestion', history.action.target_command)
        confidence = self.diagnosis_result.get('confidence', 0.0)

        server_name = ''
        metric_name = ''
        if history.alert_event:
            metric_name = history.alert_event.metric_name or ''
            if history.alert_event.server:
                server_name = history.alert_event.server.hostname
        action_name = history.action.name

        confirm_url = f"{self.base_url}/api/monitoring/callback/dingtalk/?history_id={self.history_id}&action=confirm"
        reject_url = f"{self.base_url}/api/monitoring/callback/dingtalk/?history_id={self.history_id}&action=reject"

        text = (
            f"### AIOps 修复确认\n\n"
            f"**服务器**: {server_name or '未知'}\n\n"
            f"**指标**: {metric_name}\n\n"
            f"**修复动作**: {action_name}\n\n"
            f"---\n\n"
            f"#### 根因分析\n\n{root_cause}\n\n"
            f"#### 修复建议\n\n{suggestion}\n\n"
            f"#### AI 置信度\n\n{confidence:.1%}\n\n"
        )

        return {
            "msgtype": "actionCard",
            "actionCard": {
                "title": f"AIOps 修复确认 - {action_name}",
                "text": text,
                "btnOrientation": "1",
                "btns": [
                    {"title": "确认执行", "actionURL": confirm_url},
                    {"title": "拒绝执行", "actionURL": reject_url},
                ],
            },
        }


class WeComCardBuilder:

    def __init__(self, history_id, diagnosis_result, base_url):
        self.history_id = history_id
        self.diagnosis_result = diagnosis_result
        self.base_url = base_url

    def build(self):
        history = RemediationHistory.objects.select_related(
            'action', 'alert_event__server'
        ).get(id=self.history_id)

        root_cause = self.diagnosis_result.get('root_cause', '待分析')
        suggestion = self.diagnosis_result.get('suggestion', history.action.target_command)
        confidence = self.diagnosis_result.get('confidence', 0.0)

        server_name = ''
        metric_name = ''
        if history.alert_event:
            metric_name = history.alert_event.metric_name or ''
            if history.alert_event.server:
                server_name = history.alert_event.server.hostname
        action_name = history.action.name

        confirm_url = f"{self.base_url}/api/monitoring/callback/wecom/?history_id={self.history_id}&action=confirm"
        reject_url = f"{self.base_url}/api/monitoring/callback/wecom/?history_id={self.history_id}&action=reject"

        content = (
            f"### AIOps 修复确认 - {action_name}\n"
            f"> 服务器: {server_name or '未知'}\n"
            f"> 指标: {metric_name}\n"
            f"> 根因分析: {root_cause}\n"
            f"> 修复建议: {suggestion}\n"
            f"> AI置信度: {confidence:.1%}\n\n"
            f"[确认执行]({confirm_url}) | [拒绝执行]({reject_url})"
        )

        return {
            "msgtype": "markdown",
            "markdown": {
                "content": content,
            },
        }


def send_interactive_card(history_id, diagnosis_result):
    base_url_config = SystemConfig.objects.filter(key='site_base_url').first()
    base_url = (base_url_config.value if base_url_config else getattr(settings, 'SITE_URL', 'http://localhost:8000')).rstrip('/')

    channel_config = SystemConfig.objects.filter(key='interactive_card_channel').first()
    channel = (channel_config.value if channel_config else 'dingtalk').strip().lower()

    results = []

    if channel in ('dingtalk', 'both'):
        webhook_config = SystemConfig.objects.filter(key='dingtalk_webhook').first()
        if webhook_config and webhook_config.value:
            try:
                builder = DingTalkCardBuilder(history_id, diagnosis_result, base_url)
                payload = builder.build()
                resp = requests.post(webhook_config.value, json=payload, timeout=10)
                ok = resp.status_code == 200 and resp.json().get('errcode') == 0
                results.append({'channel': 'dingtalk', 'success': ok})
                logger.info(f"[InteractiveCard] 钉钉发送: history_id={history_id}, success={ok}")
            except Exception as e:
                logger.error(f"[InteractiveCard] 钉钉发送失败: {e}")
                results.append({'channel': 'dingtalk', 'success': False, 'error': str(e)})

    if channel in ('wechat', 'both'):
        webhook_config = SystemConfig.objects.filter(key='wechat_webhook').first()
        if webhook_config and webhook_config.value:
            try:
                builder = WeComCardBuilder(history_id, diagnosis_result, base_url)
                payload = builder.build()
                resp = requests.post(webhook_config.value, json=payload, timeout=10)
                ok = resp.status_code == 200 and resp.json().get('errcode') == 0
                results.append({'channel': 'wechat', 'success': ok})
                logger.info(f"[InteractiveCard] 企微发送: history_id={history_id}, success={ok}")
            except Exception as e:
                logger.error(f"[InteractiveCard] 企微发送失败: {e}")
                results.append({'channel': 'wechat', 'success': False, 'error': str(e)})

    return results
