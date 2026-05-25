import threading
from system.models import Tenant

# 线程局部变量用于存储当前请求
_thread_locals = threading.local()


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 将当前请求存储到线程局部变量
        _thread_locals.current_request = request

        # 尝试从请求中识别租户
        request.tenant = None

        # 1. 从用户信息获取租户（如果用户已认证）
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                if hasattr(request.user, 'tenant') and request.user.tenant:
                    request.tenant = request.user.tenant
            except Exception:
                pass

        # 2. 从子域名识别租户
        if not request.tenant:
            host = request.get_host().split(':')[0]  # 去掉端口
            # 假设租户通过子域名访问，例如 tenant1.example.com
            parts = host.split('.')
            if len(parts) >= 3:  # 至少有三级域名
                subdomain = parts[0]
                try:
                    request.tenant = Tenant.objects.filter(domain=subdomain).first()
                except Exception:
                    pass

        # 3. 从请求头获取租户
        if not request.tenant:
            tenant_id = request.META.get('HTTP_X_TENANT_ID')
            if tenant_id:
                try:
                    request.tenant = Tenant.objects.filter(id=tenant_id).first()
                except Exception:
                    pass

        # 处理请求
        response = self.get_response(request)

        # 清理线程局部变量
        if hasattr(_thread_locals, 'current_request'):
            del _thread_locals.current_request

        return response


def get_current_tenant():
    """获取当前租户的辅助函数"""
    current_request = getattr(_thread_locals, 'current_request', None)
    if current_request and hasattr(current_request, 'tenant'):
        return current_request.tenant
    return None
