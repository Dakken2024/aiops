import os
import django
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ops_platform.settings')
django.setup()

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
import cmdb.routing
import k8s_manager.routing
import script_manager.routing
import monitoring.websocket.routing
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            # 合并所有应用的路由
            cmdb.routing.websocket_urlpatterns +
            k8s_manager.routing.websocket_urlpatterns +
            script_manager.routing.websocket_urlpatterns +
            monitoring.websocket.routing.websocket_urlpatterns
        )
    ),
})