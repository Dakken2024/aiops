import logging
from typing import List, Dict, Any

from monitoring.cloud_adapters.base import CloudMetric

logger = logging.getLogger(__name__)

ALIYUN_METRIC_MAP = {
    'CPUUtilization': 'cpu_usage',
    'MemoryUtilization': 'mem_usage',
    'DiskUtilization': 'disk_usage',
    'Load_1m': 'load_1min',
    'VPC_PublicIP_Input': 'net_in',
    'VPC_PublicIP_Output': 'net_out',
    'InternetInRate': 'net_in',
    'InternetOutRate': 'net_out',
    'IntranetInRate': 'net_in',
    'IntranetOutRate': 'net_out',
}

TENCENT_METRIC_MAP = {
    'CPUUsage': 'cpu_usage',
    'MemUsage': 'mem_usage',
    'DiskUsage': 'disk_usage',
    'Load_1min': 'load_1min',
    'WanInTraffic': 'net_in',
    'WanOutTraffic': 'net_out',
    'LanInTraffic': 'net_in',
    'LanOutTraffic': 'net_out',
}

PROVIDER_MAPS = {
    'aliyun': ALIYUN_METRIC_MAP,
    'tencent': TENCENT_METRIC_MAP,
}


class MetricNormalizer:
    @staticmethod
    def normalize(provider: str, metrics: List[CloudMetric]) -> List[Dict[str, Any]]:
        metric_map = PROVIDER_MAPS.get(provider, {})
        results = []
        for m in metrics:
            normalized_name = metric_map.get(m.metric_name)
            if not normalized_name:
                logger.debug(f"[Normalizer] {provider}: 跳过未映射指标 {m.metric_name}")
                continue
            results.append({
                'metric_name': normalized_name,
                'value': m.value,
                'timestamp': m.timestamp,
                'unit': m.unit,
                'original_name': m.metric_name,
                'provider': provider,
            })
        return results
