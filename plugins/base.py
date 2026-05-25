from abc import ABC, abstractmethod


class BasePlugin(ABC):
    """插件基类"""

    def __init__(self, config=None):
        self.config = config or {}

    def get_config(self, key, default=None):
        """获取配置项"""
        return self.config.get(key, default)


class BaseCollector(BasePlugin):
    """采集插件基类"""

    @abstractmethod
    def collect(self, *args, **kwargs):
        """采集数据方法"""
        pass


class BaseNotifier(BasePlugin):
    """通知插件基类"""

    @abstractmethod
    def send(self, message, *args, **kwargs):
        """发送通知方法"""
        pass


class BaseAnalyzer(BasePlugin):
    """分析插件基类"""

    @abstractmethod
    def analyze(self, data, *args, **kwargs):
        """分析数据方法"""
        pass


class BaseReporter(BasePlugin):
    """报告插件基类"""

    @abstractmethod
    def generate(self, data, *args, **kwargs):
        """生成报告方法"""
        pass
