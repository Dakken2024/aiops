import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class CloudMetric:
    def __init__(self, metric_name: str, value: float, timestamp: datetime,
                 unit: str = '', extra: Optional[Dict] = None):
        self.metric_name = metric_name
        self.value = value
        self.timestamp = timestamp
        self.unit = unit
        self.extra = extra or {}

    def to_dict(self):
        return {
            'metric_name': self.metric_name,
            'value': self.value,
            'timestamp': self.timestamp.isoformat(),
            'unit': self.unit,
            'extra': self.extra,
        }


class CloudResourceInfo:
    def __init__(self, instance_id: str, instance_name: str, resource_type: str,
                 region: str, status: str = 'Running', extra: Optional[Dict] = None):
        self.instance_id = instance_id
        self.instance_name = instance_name
        self.resource_type = resource_type
        self.region = region
        self.status = status
        self.extra = extra or {}

    def to_dict(self):
        return {
            'instance_id': self.instance_id,
            'instance_name': self.instance_name,
            'resource_type': self.resource_type,
            'region': self.region,
            'status': self.status,
            'extra': self.extra,
        }


class BaseCloudAdapter(ABC):
    provider_name: str = ''

    def __init__(self, access_key: str, secret_key: str, region: str, extra_config: Optional[Dict] = None):
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.extra_config = extra_config or {}

    @abstractmethod
    def fetch_resources(self, resource_type: str = 'ecs') -> List[CloudResourceInfo]:
        pass

    @abstractmethod
    def fetch_metrics(self, instance_id: str, resource_type: str = 'ecs',
                      metric_names: Optional[List[str]] = None,
                      period: int = 60, start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> List[CloudMetric]:
        pass

    def normalize(self, metrics: List[CloudMetric]) -> List[Dict[str, Any]]:
        from monitoring.cloud_adapters.normalizer import MetricNormalizer
        return MetricNormalizer.normalize(self.provider_name, metrics)

    def test_connection(self) -> Dict[str, Any]:
        try:
            resources = self.fetch_resources()
            return {'success': True, 'resource_count': len(resources),
                    'message': f'连接成功，发现 {len(resources)} 个资源'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
