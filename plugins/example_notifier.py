from plugins.base import BaseNotifier
import logging

logger = logging.getLogger(__name__)


class ExampleNotifier(BaseNotifier):
    """示例通知插件"""

    def send(self, message, *args, **kwargs):
        """发送通知"""
        channel = self.get_config("channel", "console")
        level = self.get_config("level", "info")

        log_message = f"[{channel.upper()}] {message}"

        if level == "info":
            logger.info(log_message)
        elif level == "warning":
            logger.warning(log_message)
        elif level == "error":
            logger.error(log_message)
        else:
            logger.debug(log_message)

        return {"status": "sent", "channel": channel, "level": level, "message": message}
