import importlib
from typing import Dict, List, Type
from system.models import Plugin
from plugins.base import (
    BasePlugin,
    BaseCollector,
    BaseNotifier,
    BaseAnalyzer,
    BaseReporter,
)


class PluginLoader:
    """插件加载器"""

    def __init__(self):
        self.plugins: Dict[str, BasePlugin] = {}

    def load_plugins(self) -> Dict[str, BasePlugin]:
        """加载所有启用的插件"""
        enabled_plugins = Plugin.objects.filter(is_enabled=True)
        self.plugins = {}

        for plugin_model in enabled_plugins:
            try:
                plugin_instance = self.instantiate_plugin(plugin_model)
                if plugin_instance:
                    self.plugins[plugin_model.name] = plugin_instance
            except Exception as e:
                print(f"Failed to load plugin {plugin_model.name}: {e}")

        return self.plugins

    def import_plugin(self, path: str):
        """动态导入插件模块"""
        try:
            module = importlib.import_module(path)
            return module
        except ImportError as e:
            raise ImportError(f"Failed to import plugin module {path}: {e}")

    def instantiate_plugin(self, plugin_model: Plugin) -> BasePlugin:
        """实例化插件"""
        module = self.import_plugin(plugin_model.path)

        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type):
                if plugin_model.type == "collector" and issubclass(attr, BaseCollector) and attr != BaseCollector:
                    plugin_class = attr
                    break
                elif plugin_model.type == "notifier" and issubclass(attr, BaseNotifier) and attr != BaseNotifier:
                    plugin_class = attr
                    break
                elif plugin_model.type == "analyzer" and issubclass(attr, BaseAnalyzer) and attr != BaseAnalyzer:
                    plugin_class = attr
                    break
                elif plugin_model.type == "reporter" and issubclass(attr, BaseReporter) and attr != BaseReporter:
                    plugin_class = attr
                    break

        if not plugin_class:
            raise ValueError(f"No valid plugin class found in {plugin_model.path} for type {plugin_model.type}")

        config = plugin_model.get_config()
        return plugin_class(config=config)

    def get_plugin(self, name: str) -> BasePlugin:
        """获取已加载的插件"""
        return self.plugins.get(name)

    def get_plugins_by_type(self, plugin_type: str) -> List[BasePlugin]:
        """按类型获取插件"""
        return [
            plugin for name, plugin in self.plugins.items()
            if self._get_plugin_type(plugin) == plugin_type
        ]

    def _get_plugin_type(self, plugin: BasePlugin) -> str:
        """获取插件类型"""
        if isinstance(plugin, BaseCollector):
            return "collector"
        elif isinstance(plugin, BaseNotifier):
            return "notifier"
        elif isinstance(plugin, BaseAnalyzer):
            return "analyzer"
        elif isinstance(plugin, BaseReporter):
            return "reporter"
        return "unknown"


plugin_loader = PluginLoader()
