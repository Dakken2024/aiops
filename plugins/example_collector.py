from plugins.base import BaseCollector
import datetime


class ExampleCollector(BaseCollector):
    """示例采集插件"""

    def collect(self, *args, **kwargs):
        """采集数据"""
        source = self.get_config("source", "default")
        limit = self.get_config("limit", 10)

        data = []
        for i in range(limit):
            data.append({
                "id": i + 1,
                "source": source,
                "timestamp": datetime.datetime.now().isoformat(),
                "value": f"Sample data {i + 1}"
            })

        return data
