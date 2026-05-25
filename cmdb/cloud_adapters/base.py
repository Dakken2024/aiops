"""
多云适配器抽象基类
定义所有云厂商适配器必须实现的接口与统一指标格式转换逻辑。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseCloudAdapter(ABC):
    """
    云厂商适配器抽象基类。

    子类必须实现：
      - authenticate(): 完成云厂商身份认证/客户端初始化。
      - fetch_metrics(): 从云监控拉取原始指标数据。
    """

    def __init__(self, cloud_account: Any):
        """
        :param cloud_account: CloudAccount 模型实例，必须包含 access_key / secret_key / region 等字段。
        """
        self.cloud_account = cloud_account
        self.client = None  # 由 authenticate() 赋值为云厂商 SDK 客户端

    @abstractmethod
    def authenticate(self) -> None:
        """
        使用 cloud_account 中的凭据初始化云厂商客户端。
        失败时应抛出异常，由上层捕获并记录。
        """
        ...

    @abstractmethod
    def fetch_metrics(
        self,
        resource_type: str,
        instance_id: str,
        metric_names: List[str],
        start_time: Any,
        end_time: Any,
    ) -> List[Dict[str, Any]]:
        """
        拉取指定资源的监控指标。

        :param resource_type: 资源类型，如 ecs / rds / slb 等。
        :param instance_id: 云厂商实例 ID。
        :param metric_names: 指标名称列表，如 ['CPUUsage', 'MemoryUsage']。
        :param start_time: 起始时间（datetime 或时间戳）。
        :param end_time: 结束时间（datetime 或时间戳）。
        :return: 原始指标数据列表，元素为云厂商返回的原始 dict。
        """
        ...

    def normalize_metric(self, raw_metric: Dict[str, Any]) -> Dict[str, Any]:
        """
        将云厂商原始指标转换为统一内部格式。

        统一格式：
        {
            "server_id":   str | None,   # 关联的本地 Server ID（如已知）
            "metric_name": str,          # 标准化指标名，如 cpu_usage
            "value":       float,        # 指标数值
            "timestamp":   str | float,  # ISO8601 或 Unix 时间戳
            "labels":      dict,         # 额外维度，如 {"disk": "/dev/vda1"}
        }

        子类可覆盖此方法以适配各云厂商不同的字段命名。
        """
        return {
            "server_id": raw_metric.get("server_id"),
            "metric_name": raw_metric.get("metric_name", "unknown"),
            "value": float(raw_metric.get("value", 0.0)),
            "timestamp": raw_metric.get("timestamp"),
            "labels": raw_metric.get("labels", {}),
        }
