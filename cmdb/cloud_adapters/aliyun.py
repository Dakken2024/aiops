"""
阿里云适配器
支持通过阿里云 CloudMonitor 获取 ECS 等指标。
若未安装阿里云 SDK，则自动降级为 Mock 实现，便于本地测试。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List

from .base import BaseCloudAdapter

logger = logging.getLogger(__name__)

# 尝试导入阿里云 SDK；若缺失则标记 _ALIYUN_SDK_AVAILABLE = False
try:
    from aliyunsdkcore.client import AcsClient
    from aliyunsdkcore.request import CommonRequest
    from aliyunsdkecs.request.v20140526.DescribeInstancesRequest import (
        DescribeInstancesRequest,
    )

    _ALIYUN_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover
    AcsClient = None  # type: ignore
    CommonRequest = None  # type: ignore
    DescribeInstancesRequest = None  # type: ignore
    _ALIYUN_SDK_AVAILABLE = False


class AliyunAdapter(BaseCloudAdapter):
    """
    阿里云适配器实现。
    """

    def authenticate(self) -> None:
        """
        使用 CloudAccount 中的 access_key / secret_key 初始化 AcsClient。
        region 默认使用 cloud_account.region，若为空则回退到 cn-hangzhou。
        """
        if not _ALIYUN_SDK_AVAILABLE:
            logger.warning("[AliyunAdapter] 阿里云 SDK 未安装，进入 Mock 模式")
            self.client = None
            return

        account = self.cloud_account
        region = getattr(account, "region", None) or "cn-hangzhou"
        access_key = getattr(account, "access_key", None) or ""
        secret_key = getattr(account, "secret_key", None) or ""

        if not access_key or not secret_key:
            raise ValueError("[AliyunAdapter] access_key 或 secret_key 为空，无法认证")

        try:
            self.client = AcsClient(
                ak=access_key,
                secret=secret_key,
                region_id=region,
            )
            logger.info("[AliyunAdapter] AcsClient 初始化成功，region=%s", region)
        except Exception as exc:
            logger.error("[AliyunAdapter] AcsClient 初始化失败: %s", exc)
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
        拉取阿里云 CloudMonitor 指标（当前仅实现 ECS 维度）。
        时间参数接受 datetime 或 ISO8601 字符串。
        """
        if not _ALIYUN_SDK_AVAILABLE or self.client is None:
            logger.warning("[AliyunAdapter] SDK 不可用，返回 Mock 指标数据")
            return self._mock_metrics(instance_id, metric_names)

        if resource_type != "ecs":
            logger.warning("[AliyunAdapter] 当前仅支持 ecs 资源类型，收到 %s", resource_type)

        # 统一时间格式为 ISO8601（阿里云要求 YYYY-MM-DDTHH:mm:ssZ）
        start_str = self._format_time(start_time)
        end_str = self._format_time(end_time)

        results: List[Dict[str, Any]] = []

        for metric_name in metric_names:
            try:
                req = CommonRequest()
                req.set_accept_format("json")
                req.set_domain("metrics.cn-hangzhou.aliyuncs.com")
                req.set_method("POST")
                req.set_protocol_type("https")
                req.set_version("2019-01-01")
                req.set_action_name("DescribeMetricList")

                req.add_query_param("Namespace", "acs_ecs_dashboard")
                req.add_query_param("MetricName", metric_name)
                req.add_query_param("Dimensions", f'{{"instanceId":"{instance_id}"}}')
                req.add_query_param("StartTime", start_str)
                req.add_query_param("EndTime", end_str)
                req.add_query_param("Period", "60")

                response = self.client.do_action_with_exception(req)
                # response 为 bytes，需解码；为简化处理，直接记录并包装为原始 dict
                results.append(
                    {
                        "provider": "aliyun",
                        "resource_type": resource_type,
                        "instance_id": instance_id,
                        "metric_name": metric_name,
                        "raw_response": response.decode("utf-8") if isinstance(response, bytes) else str(response),
                        "start_time": start_str,
                        "end_time": end_str,
                    }
                )
            except Exception as exc:
                logger.error(
                    "[AliyunAdapter] 获取指标 %s 失败 (instance=%s): %s",
                    metric_name,
                    instance_id,
                    exc,
                )
                # 继续获取下一个指标，避免单点失败导致全部中断
                continue

        return results

    def normalize_metric(self, raw_metric: Dict[str, Any]) -> Dict[str, Any]:
        """
        将阿里云返回的原始指标转换为统一内部格式。
        若 raw_metric 中包含解析后的 datapoints，可直接提取 value / timestamp。
        """
        # 优先使用已解析字段，否则回退到基类通用转换
        datapoints = raw_metric.get("datapoints")
        if isinstance(datapoints, list) and datapoints:
            dp = datapoints[0]
            return {
                "server_id": raw_metric.get("server_id"),
                "metric_name": raw_metric.get("metric_name", "unknown"),
                "value": float(dp.get("Average", 0.0)),
                "timestamp": dp.get("timestamp"),
                "labels": raw_metric.get("labels", {}),
            }
        return super().normalize_metric(raw_metric)

    # --------------------------------------------------------------------- #
    # 内部辅助方法
    # --------------------------------------------------------------------- #

    @staticmethod
    def _format_time(t: Any) -> str:
        """将 datetime 或字符串转换为阿里云要求的 ISO8601 UTC 格式。"""
        if isinstance(t, datetime):
            return t.strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(t, str):
            return t
        # 假设为时间戳（秒或毫秒）
        try:
            ts = float(t)
            if ts > 1e11:  # 毫秒级时间戳
                ts = ts / 1000.0
            return datetime.utcfromtimestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            return str(t)

    @staticmethod
    def _mock_metrics(instance_id: str, metric_names: List[str]) -> List[Dict[str, Any]]:
        """
        Mock 实现：当阿里云 SDK 未安装时返回固定结构的伪数据，用于测试。
        """
        import random
        from datetime import datetime, timezone

        base_time = datetime.now(timezone.utc).isoformat()
        results = []
        for name in metric_names:
            results.append(
                {
                    "provider": "aliyun",
                    "resource_type": "ecs",
                    "instance_id": instance_id,
                    "metric_name": name,
                    "value": round(random.uniform(0, 100), 2),
                    "timestamp": base_time,
                    "labels": {"mock": True},
                }
            )
        return results
