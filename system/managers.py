from django.db import models


class TenantManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        # 尝试从请求上下文中获取租户
        try:
            from django.utils.deprecation import MiddlewareMixin
            from django.conf import settings
            # 这里我们会通过中间件设置的线程局部变量来获取当前租户
            import threading
            current_request = getattr(threading.local(), 'current_request', None)
            if current_request and hasattr(current_request, 'tenant') and current_request.tenant:
                return queryset.filter(tenant=current_request.tenant)
        except Exception:
            pass
        return queryset
