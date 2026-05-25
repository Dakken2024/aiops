import logging
from datetime import datetime, timedelta
from typing import List, Optional

from monitoring.cloud_adapters.base import BaseCloudAdapter, CloudMetric, CloudResourceInfo

logger = logging.getLogger(__name__)

CVM_METRICS = [
    'CPUUsage', 'MemUsage', 'DiskUsage',
    'Load_1min', 'WanOutTraffic', 'WanInTraffic',
]


class TencentAdapter(BaseCloudAdapter):
    provider_name = 'tencent'

    def fetch_resources(self, resource_type: str = 'ecs') -> List[CloudResourceInfo]:
        from tencentcloud.common import credential
        from tencentcloud.cvm.v20170312 import cvm_client, models as cvm_models

        cred = credential.Credential(self.access_key, self.secret_key)
        client = cvm_client.CvmClient(cred, self.region)

        req = cvm_models.DescribeInstancesRequest()
        req.from_json_string('{}')

        results = []
        try:
            resp = client.DescribeInstances(req)
            for inst in resp.InstanceSet:
                private_ips = inst.PrivateIpAddresses or ['']
                public_ips = inst.PublicIpAddresses or ['']
                results.append(CloudResourceInfo(
                    instance_id=inst.InstanceId,
                    instance_name=inst.InstanceName,
                    resource_type='ecs',
                    region=self.region,
                    status='Running' if inst.InstanceState == 'RUNNING' else 'Stopped',
                    extra={
                        'cpu': inst.CPU,
                        'memory': inst.Memory,
                        'os': inst.OsName,
                        'instance_type': inst.InstanceType,
                        'private_ip': private_ips[0],
                        'public_ip': public_ips[0] if public_ips else '',
                    },
                ))
        except Exception as e:
            logger.error(f"[TencentAdapter] 拉取资源失败: {e}")
        return results

    def fetch_metrics(self, instance_id: str, resource_type: str = 'ecs',
                      metric_names: Optional[List[str]] = None,
                      period: int = 60, start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> List[CloudMetric]:
        from tencentcloud.common import credential
        from tencentcloud.monitor.v20180724 import monitor_client, models as mon_models

        if not metric_names:
            metric_names = CVM_METRICS
        if not end_time:
            end_time = datetime.utcnow()
        if not start_time:
            start_time = end_time - timedelta(minutes=5)

        cred = credential.Credential(self.access_key, self.secret_key)
        client = monitor_client.MonitorClient(cred, self.region)
        results = []

        for metric_name in metric_names:
            try:
                req = mon_models.GetMonitorDataRequest()
                req.Namespace = 'QCE/CVM'
                req.MetricName = metric_name
                req.Period = period
                req.StartTime = start_time.strftime('%Y-%m-%d %H:%M:%S')
                req.EndTime = end_time.strftime('%Y-%m-%d %H:%M:%S')
                req.Instances = [{'Dimensions': [{'Name': 'InstanceId', 'Value': instance_id}]}]

                resp = client.GetMonitorData(req)
                for dp in resp.DataPoints:
                    if dp.Timestamps and dp.Values:
                        for ts, val in zip(dp.Timestamps, dp.Values):
                            results.append(CloudMetric(
                                metric_name=metric_name,
                                value=float(val),
                                timestamp=datetime.fromtimestamp(ts),
                                unit=resp.Unit or '',
                            ))
            except Exception as e:
                logger.debug(f"[TencentAdapter] 指标{metric_name}拉取失败: {e}")

        return results
