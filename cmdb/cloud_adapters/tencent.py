"""
腾讯云适配器
支持通过腾讯云云监控（Monitor）获取 CVM 等指标。
若未安装腾讯云 SDK，则自动降级为 Mock 实现，便于本地测试。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseCloudAdapter

logger = logging.getLogger(__name__)

# 尝试导入腾讯云 SDK；若缺失则标记 _TENCENT_SDK_AVAILABLE = False
try:
    from tencentcloud.common.credential import Credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.monitor.v20180724 import monitor_client, models as monitor_models

    _TENCENT_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    Credential = None  # type: ignore
    ClientProfile = None  # type: ignore
    HttpProfile = None  # type: ignore
    monitor_client = None  # type: ignore
    monitor_models = None  # type: ignore
    _TENCENT_SDK_AVAILABLE = False


class TencentAdapter(BaseCloudAdapter):
    """
    腾讯云适配器实现。
    """

    def authenticate(self) -> None:
        """
        使用 CloudAccount 中的 access_key / secret_key 初始化腾讯云 Monitor 客户端。
        region 默认使用 cloud_account.region，若为空则回退到 ap-guangzhou。
        """
        if not _TENCENT_SDK_AVAILABLE:
            logger.warning("[TencentAdapter] 腾讯云 SDK 未安装，进入 Mock 模式")
            self.client = None
            return

        account = self.cloud_account
        region = getattr(account, "region", None) or "ap-guangzhou"
        access_key = getattr(account, "access_key", None) or ""
        secret_key = getattr(account, "secret_key", None) or ""

        if not access_key or not secret_key:
            raise ValueError("[TencentAdapter] access_key 或 secret_key 为空，无法认证")

        try:
            cred = Credential(access_key, secret_key)
            http_profile = HttpProfile()
            http_profile.endpoint = "monitor.tencentcloudapi.com"
            client_profile = ClientProfile()
            client_profile.httpProfile = http_profile

            self.client = monitor_client.MonitorClient(cred, region, client_profile)
            logger.info("[TencentAdapter] MonitorClient 初始化成功，region=%s", region)
        except Exception as exc:
            logger.error("[TencentAdapter] MonitorClient 初始化失败: %s", exc)
            raise

    def fetch_metrics(
        self,
        resource_type: str,
        instance_id: str,
        metric_names: List[str],
        start_time: Any,
        end_time: Any,
    ) -> List[Dict[str, Any]]:
        """
        拉取腾讯云云监控指标（当前仅实现 CVM 维度）。
        时间参数接受 datetime 或 ISO8601 字符串。
        """
        if not _TENCENT_SDK_AVAILABLE or self.client is None:
            logger.warning("[TencentAdapter] SDK 不可用，返回 Mock 指标数据")
            return self._mock_metrics(instance_id, metric_names)

        if resource_type != "ecs":
            logger.warning("[TencentAdapter] 当前仅支持 ecs 资源类型，收到 %s", resource_type)

        start_str = self._format_time(start_time)
        end_str = self._format_time(end_time)

        results: List[Dict[str, Any]] = []

        for metric_name in metric_names:
            try:
                req = monitor_models.GetMonitorDataRequest()
                req.Namespace = "QCE/CVM"
                req.MetricName = metric_name
                req.Instances = [
                    {
                        "Dimensions": [
                            {"Name": "InstanceId", "Value": instance_id}
                        ]
                    }
                ]
                req.Period = 60
                req.StartTime = start_str
                req.EndTime = end_str

                response = self.client.GetMonitorData(req)
                # response 为 SDK 模型对象，序列化为 dict 后包装
                resp_dict = response.to_json_string() if hasattr(response, "to_json_string") else str(response)
                results.append(
                    {
                        "provider": "tencent",
                        "resource_type": resource_type,
                        "instance_id": instance_id,
                        "metric_name": metric_name,
                        "raw_response": resp_dict,
                        "start_time": start_str,
                        "end_time": end_str,
                    }
                )
            except Exception as exc:
                logger.error(
                    "[TencentAdapter] 获取指标 %s 失败 (instance=%s): %s",
                    metric_name,
                    instance_id,
                    exc,
                )
                continue

        return results

    def normalize_metric(self, raw_metric: Dict[str, Any]) -> Dict[str, Any]:
        """
        将腾讯云返回的原始指标转换为统一内部格式。
        若 raw_metric 中包含解析后的 DataPoints，可直接提取 value / timestamp。
        """
        datapoints = raw_metric.get("DataPoints")
        if isinstance(datapoints, list) and datapoints:
            dp = datapoints[0]
            # 腾讯云 DataPoints 通常为 [{"Timestamps":[...], "Values":[...]}]
            timestamps = dp.get("Timestamps", [])
            values = dp.get("Values", [])
            if timestamps and values:
                return {
                    "server_id": raw_metric.get("server_id"),
                    "metric_name": raw_metric.get("metric_name", "unknown"),
                    "value": float(values[0]),
                    "timestamp": timestamps[0],
                    "labels": raw_metric.get("labels", {}),
                }
        return super().normalize_metric(raw_metric)

    # --------------------------------------------------------------------- #
    # 内部辅助方法
    # --------------------------------------------------------------------- #

    @staticmethod
    def _format_time(t: Any) -> str:
        """将 datetime 或字符串转换为腾讯云要求的 ISO8601 格式。"""
        if isinstance(t, datetime):
            return t.strftime("%Y-%m-%dT%H:%M:%S%z")
        if isinstance(t, str):
            return t
        try:
            ts = float(t)
            if ts > 1e11:
                ts = ts / 1000.0
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return str(t)

    @staticmethod
    def _mock_metrics(instance_id: str, metric_names: List[str]) -> List[Dict[str, Any]]:
        """
        Mock 实现：当腾讯云 SDK 未安装时返回固定结构的伪数据，用于测试。
        """
        import random
        from datetime import datetime, timezone

        base_time = datetime.now(timezone.utc).isoformat()
        results = []
        for name in metric_names:
            results.append(
                {
                    "provider": "tencent",
                    "resource_type": "ecs",
                    "instance_id": instance_id,
                    "metric_name": name,
                    "value": round(random.uniform(0, 100), 2),
                    "timestamp": base_time,
                    "labels": {"mock": True},
                }
            )
        return results
