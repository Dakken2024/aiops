from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # 路由格式: /ws/k8s/log/<cluster_id>/<namespace>/<pod_name>/
    re_path(r'ws/k8s/log/(?P<cluster_id>\w+)/(?P<namespace>[\w-]+)/(?P<pod_name>[\w-]+)/$', consumers.K8sLogConsumer.as_asgi()),
]