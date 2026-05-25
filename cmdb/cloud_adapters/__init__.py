"""
多云适配器入口模块

导出：
  - BaseCloudAdapter: 抽象基类，定义统一接口。
  - AliyunAdapter:    阿里云适配器实现。
  - TencentAdapter:   腾讯云适配器实现。

使用示例：
    from cmdb.cloud_adapters import AliyunAdapter
    adapter = AliyunAdapter(cloud_account)
    adapter.authenticate()
    raw_metrics = adapter.fetch_metrics('ecs', 'i-xxx', ['CPUUsage'], start, end)
    normalized = [adapter.normalize_metric(m) for m in raw_metrics]
"""

from .base import BaseCloudAdapter
from .aliyun import AliyunAdapter
from .tencent import TencentAdapter

__all__ = [
    "BaseCloudAdapter",
    "AliyunAdapter",
    "TencentAdapter",
]
