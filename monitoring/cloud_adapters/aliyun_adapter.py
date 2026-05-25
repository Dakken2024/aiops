import logging
from datetime import datetime, timedelta
from typing import List, Optional

from monitoring.cloud_adapters.base import BaseCloudAdapter, CloudMetric, CloudResourceInfo

logger = logging.getLogger(__name__)

ECS_METRICS = [
    'CPUUtilization', 'MemoryUtilization', 'DiskUtilization',
    'Load_1m', 'InternetInRate', 'InternetOutRate',
]


class AliyunAdapter(BaseCloudAdapter):
    provider_name = 'aliyun'

    def fetch_resources(self, resource_type: str = 'ecs') -> List[CloudResourceInfo]:
        from aliyunsdkcore.client import AcsClient
        from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import DescribeInstancesRequest

        client = AcsClient(self.access_key, self.secret_key, self.region)
        request = DescribeInstancesRequest()
        request.set_PageSize(100)

        results = []
        try:
            response = client.do_action_with_exception(request)
            import json
            data = json.loads(response)
            for inst in data.get('Instances', {}).get('Instance', []):
                results.append(CloudResourceInfo(
                    instance_id=inst.get('InstanceId', ''),
                    instance_name=inst.get('InstanceName', ''),
                    resource_type='ecs',
                    region=inst.get('RegionId', self.region),
                    status=inst.get('Status', 'Stopped'),
                    extra={
                        'cpu': inst.get('Cpu', ''),
                        'memory': inst.get('Memory', ''),
                        'os': inst.get('OSName', ''),
                        'instance_type': inst.get('InstanceType', ''),
                        'private_ip': (inst.get('VpcAttributes', {})
                                       .get('PrivateIpAddress', {}).get('IpAddress', [''])[0]),
                        'public_ip': (inst.get('PublicIpAddress', {}).get('IpAddress', [''])[0]),
                    },
                ))
        except Exception as e:
            logger.error(f"[AliyunAdapter] 拉取资源失败: {e}")
        return results

    def fetch_metrics(self, instance_id: str, resource_type: str = 'ecs',
                      metric_names: Optional[List[str]] = None,
                      period: int = 60, start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> List[CloudMetric]:
        from aliyunsdkcore.client import AcsClient

        if not metric_names:
            metric_names = ECS_METRICS
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(minutes=5)

        client = AcsClient(self.access_key, self.secret_key, self.region)
        results = []

        for metric_name in metric_names:
            try:
                metric_data = self._fetch_single_metric(
                    client, instance_id, metric_name, period, start_time, end_time
                )
                results.extend(metric_data)
            except Exception as e:
                logger.debug(f"[AliyunAdapter] 指标{metric_name}拉取失败: {e}")

        return results

    def _fetch_single_metric(self, client, instance_id, metric_name, period, start_time, end_time):
        from aliyunsdkcore.acs_exception.exceptions import ServerException
        try:
            from aliyunsdkcms.request.v20190101.QueryMetricListRequest import QueryMetricListRequest
        except ImportError:
            try:
                from aliyunsdkcms.request.v20180308.QueryMetricListRequest import QueryMetricListRequest
            except ImportError:
                logger.warning("[AliyunAdapter] CMS SDK 未安装，跳过指标拉取")
                return []

        request = QueryMetricListRequest()
        request.set_Project('acs_ecs_dashboard')
        request.set_Metric(metric_name)
        request.set_Period(str(period))
        request.set_StartTime(start_time.strftime('%Y-%m-%d %H:%M:%S'))
        request.set_EndTime(end_time.strftime('%Y-%m-%d %H:%M:%S'))
        request.set_Dimensions(f"{{\"instanceId\":\"{instance_id}\"}}")

        import json
        results = []
        try:
            response = client.do_action_with_exception(request)
            data = json.loads(response)
            datapoints = data.get('Datapoints', '[]')
            if isinstance(datapoints, str):
                datapoints = json.loads(datapoints)
            for dp in datapoints:
                ts = datetime.fromtimestamp(dp.get('timestamp', 0) / 1000)
                results.append(CloudMetric(
                    metric_name=metric_name,
                    value=float(dp.get('Value', dp.get('Average', 0))),
                    timestamp=ts,
                    unit=dp.get('unit', ''),
                ))
        except Exception as e:
            logger.debug(f"[AliyunAdapter] {metric_name} 拉取异常: {e}")

        return results
