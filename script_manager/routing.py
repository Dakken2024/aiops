from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    # 匹配 /ws/task/log/<task_id>/
    re_path(r'ws/task/log/(?P<task_id>\d+)/$', consumers.TaskLogConsumer.as_asgi()),
]