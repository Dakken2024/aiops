from monitoring.cloud_adapters.base import BaseCloudAdapter
from monitoring.cloud_adapters.registry import AdapterRegistry
from monitoring.cloud_adapters.normalizer import MetricNormalizer

def _auto_register():
    try:
        from monitoring.cloud_adapters.aliyun_adapter import AliyunAdapter
        AdapterRegistry.register('aliyun', AliyunAdapter)
    except ImportError:
        pass
    try:
        from monitoring.cloud_adapters.tencent_adapter import TencentAdapter
        AdapterRegistry.register('tencent', TencentAdapter)
    except ImportError:
        pass

_auto_register()

__all__ = ['BaseCloudAdapter', 'AdapterRegistry', 'MetricNormalizer']
