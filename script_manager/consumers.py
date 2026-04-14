# script_manager/consumers.py
import json
from channels.generic.websocket import AsyncWebsocketConsumer

class TaskLogConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # 从 URL 获取 task_id
        self.task_id = self.scope['url_route']['kwargs']['task_id']
        self.group_name = f"task_{self.task_id}"

        # 加入组
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    # 接收来自 Celery 的消息并转发给 WebSocket 客户端
    async def task_log_message(self, event):
        message = event['message']
        await self.send(text_data=json.dumps({
            'message': message
        }))