import logging
from typing import Dict, Type, Optional

from monitoring.cloud_adapters.base import BaseCloudAdapter

logger = logging.getLogger(__name__)


class AdapterRegistry:
    _adapters: Dict[str, Type[BaseCloudAdapter]] = {}

    @classmethod
    def register(cls, provider_name: str, adapter_class: Type[BaseCloudAdapter]):
        cls._adapters[provider_name] = adapter_class
        logger.info(f"[AdapterRegistry] 注册适配器: {provider_name} -> {adapter_class.__name__}")

    @classmethod
    def get_adapter_class(cls, provider_name: str) -> Optional[Type[BaseCloudAdapter]]:
        return cls._adapters.get(provider_name)

    @classmethod
    def get_adapter(cls, provider_name: str, **kwargs) -> Optional[BaseCloudAdapter]:
        adapter_class = cls._adapters.get(provider_name)
        if not adapter_class:
            logger.error(f"[AdapterRegistry] 未注册的云厂商: {provider_name}")
            return None
        return adapter_class(**kwargs)

    @classmethod
    def list_adapters(cls) -> Dict[str, str]:
        return {name: cls_.__name__ for name, cls_ in cls._adapters.items()}

    @classmethod
    def from_cloud_account(cls, cloud_account) -> Optional[BaseCloudAdapter]:
        return cls.get_adapter(
            provider_name=cloud_account.type,
            access_key=cloud_account.access_key,
            secret_key=cloud_account.secret_key,
            region=cloud_account.region,
            extra_config=cloud_account.extra_config if hasattr(cloud_account, 'extra_config') else {},
        )
